#!/usr/bin/env node

/**
 * @fileoverview Map. Think. Do. MCP Server implementation.
 *
 * This server provides a tool for reflective problem-solving in software development,
 * allowing decomposition of tasks into sequential, revisable, and branchable thoughts.
 * It adheres to the Model Context Protocol (MCP) using SDK version 1.11.0 and is designed
 * to integrate seamlessly with Claude Desktop or similar MCP-compliant clients.
 *
 * ## Key Features
 * - Processes "thoughts" in structured JSON with sequential numbering
 * - Supports advanced reasoning patterns through branching and revision semantics
 *   - Branching: Explore alternative approaches from any existing thought
 *   - Revision: Correct or update earlier thoughts when new insights emerge
 * - Implements MCP capabilities for tools, resources, and prompts
 * - Uses custom FilteredStdioServerTransport for improved stability
 * - Provides detailed validation and error handling with helpful guidance
 * - Logs thought evolution to stderr for debugging and visibility
 *
 * ## Remote / SSE Mode
 * - `--sse` exposes an HTTP/SSE MCP server
 * - `--local` binds to LAN IP for local network access
 * - `--remote` exposes via public tunnel (ngrok, pinggy, localhostrun, etc.)
 * - Token auth via `--token` or `--token-file`
 * - Grok-compatible POST /sse fallback
 *
 * ## MCP Protocol Communication
 * - IMPORTANT: Local MCP servers must never log to stdout (standard output)
 * - All logging must be directed to stderr using console.error() instead of console.log()
 * - The stdout channel is reserved exclusively for JSON-RPC protocol messages
 * - Using console.log() or console.info() will cause client-side parsing errors
 *
 * @version 0.7.0
 * @mcp-sdk-version 1.11.0
 */

import process from 'node:process';
import { randomUUID } from 'node:crypto';
import { Server } from '@modelcontextprotocol/sdk/server/index.js';
import http from 'node:http';
import https from 'node:https';
import { URL } from 'node:url';
import { spawn, execSync, type ChildProcess } from 'node:child_process';
import { SSEServerTransport } from '@modelcontextprotocol/sdk/server/sse.js';
import {
  CallToolRequestSchema,
  CompleteRequestSchema,
  GetPromptRequestSchema,
  JSONRPCMessageSchema,
  ListPromptsRequestSchema,
  ListResourcesRequestSchema,
  ListToolsRequestSchema,
  ServerCapabilities,
  Tool,
  type ServerResult,
  McpError,
  ErrorCode,
} from '@modelcontextprotocol/sdk/types.js';
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js';
import { z, ZodError } from 'zod';
import { zodToJsonSchema } from 'zod-to-json-schema';
import { PromptManager } from './prompts/manager.js';
import { configManager, type MapThinkDoConfig } from './utils/config-manager.js';
import {
  CONFIG_DIR,
  DEFAULT_CONFIG_DIR,
  LEGACY_CONFIG_DIR,
  MAX_THOUGHT_LENGTH,
  MAX_THOUGHTS,
  MAX_PREVIOUS_THOUGHTS_CONTEXT,
  CUSTOM_PROMPTS_DIR,
} from './utils/config.js';
import { ActionRanking, CognitiveOrchestrator } from './cognitive/cognitive-orchestrator.js';
import { createCognitiveOrchestrator } from './cognitive/cognitive-orchestrator-factory.js';
import { Mutex } from './utils/mutex.js';
import { StoredThought, ReasoningSession } from './memory/memory-store.js';
import { SQLiteStore } from './memory/sqlite-store.js';
import { BiasDetector } from './cognitive/bias-detector.js';
import { secureLogger } from './utils/secure-logger.js';
import { MCPIntegrationManager } from './cognitive/mcp-manager.js';
import { formatObjectNumbers } from './utils/number-formatter.js';
import path from 'path';
import os from 'os';
import fs from 'node:fs';

/* -------------------------------------------------------------------------- */
/*                               CONFIGURATION                                */
/* -------------------------------------------------------------------------- */

export const GENERIC_PROCESSING_ERROR_MESSAGE =
  'An unexpected internal error occurred while processing the thought. Retry with a simpler thought or try again later.';
export const GENERIC_PROMPT_ERROR_MESSAGE = 'Prompt processing failed.';

// Compile-time enum -> const enum would be erased, but we keep values for logs.
export enum LogLevel {
  ERROR = 0,
  WARN = 1,
  INFO = 2,
  DEBUG = 3,
}

/* -------------------------------------------------------------------------- */
/*                               DATA SCHEMAS                                 */
/* -------------------------------------------------------------------------- */

export interface ThoughtData {
  thought: string;
  thought_number: number;
  total_thoughts: number;
  next_thought_needed: boolean;
  is_revision?: boolean;
  revises_thought?: number;
  branch_from_thought?: number;
  branch_id?: string;
  needs_more_thoughts?: boolean;
}

const ThoughtDataSchema = z
  .object({
    thought: z
      .string()
      .trim()
      .min(1, 'Thought cannot be empty.')
      .max(MAX_THOUGHT_LENGTH, `Thought exceeds ${MAX_THOUGHT_LENGTH} chars.`),
    thought_number: z.number().int().positive(),
    total_thoughts: z.number().int().positive(),
    next_thought_needed: z.boolean(),
    is_revision: z.boolean().optional(),
    revises_thought: z.number().int().positive().optional(),
    branch_from_thought: z.number().int().positive().optional(),
    branch_id: z.string().trim().min(1).optional(),
    needs_more_thoughts: z.boolean().optional(),
  })
  .strict()
  .refine(
    d =>
      d.is_revision
        ? typeof d.revises_thought === 'number' && !d.branch_id && !d.branch_from_thought
        : true,
    {
      message: 'If is_revision=true, provide revises_thought and omit branch_* fields.',
    }
  )
  .refine(d => (!d.is_revision && d.revises_thought === undefined) || d.is_revision, {
    message: 'revises_thought only allowed when is_revision=true.',
  })
  .refine(
    d =>
      d.branch_id || d.branch_from_thought
        ? d.branch_id !== undefined && d.branch_from_thought !== undefined && !d.is_revision
        : true,
    {
      message: 'branch_id and branch_from_thought required together and not with revision.',
    }
  );

export type ValidatedThoughtData = z.infer<typeof ThoughtDataSchema>;

export function validateThoughtData(input: unknown): ValidatedThoughtData {
  return ThoughtDataSchema.parse(input);
}

/**
 * Cached JSON schema: avoids rebuilding on every ListTools call.
 */
const THOUGHT_DATA_JSON_SCHEMA = Object.freeze(
  zodToJsonSchema(ThoughtDataSchema, { target: 'jsonSchema7' }) as Record<string, unknown>
);

/**
 * Schema for outcome feedback on a prior reasoning session. Closes the learning
 * loop: clients report how a session actually turned out so the server can
 * calibrate confidence and learn from real outcomes.
 */
const FeedbackDataSchema = z
  .object({
    session_id: z.string().trim().min(1).max(200),
    outcome: z.enum(['success', 'failure', 'partial']),
    score: z.number().min(0).max(1),
    comment: z.string().trim().max(2000).optional(),
  })
  .strict();

export type ValidatedFeedbackData = z.infer<typeof FeedbackDataSchema>;

export function validateFeedbackData(input: unknown): ValidatedFeedbackData {
  return FeedbackDataSchema.parse(input);
}

const FEEDBACK_DATA_JSON_SCHEMA = Object.freeze(
  zodToJsonSchema(FeedbackDataSchema, { target: 'jsonSchema7' }) as Record<string, unknown>
);

/* -------------------------------------------------------------------------- */
/*                                  TOOL DEF                                  */
/* -------------------------------------------------------------------------- */

export const PLAN_AUDIT_MAP_TOOL_NAME = 'plan-audit-map';
export const LEGACY_TOOL_NAME = 'code-reasoning';

export const PLAN_AUDIT_MAP_TOOL: Tool = {
  name: PLAN_AUDIT_MAP_TOOL_NAME,
  description: ` Map. Think. Do. - Structured cognitive reasoning for complex problem-solving.

This tool helps you MAP problems, THINK through solutions, and DO what needs to be done through
structured reasoning with multiple cognitive perspectives, persisted state, and heuristic cognitive metadata.

 MAP - Understand the Problem:
- Break down complex problems into manageable parts
- Identify constraints, dependencies, and unknowns
- Establish context and gather relevant information

 THINK - Reason Through Solutions:
- Apply multiple cognitive perspectives to the problem
- Detect and correct cognitive biases in reasoning
- Generate insights and identify breakthrough opportunities
- Reuse persisted context and historical patterns when available

 DO - Execute with Confidence:
- Synthesize reasoning into actionable steps
- Track progress through structured thought sequences
- Revise and branch when new insights emerge

 COGNITIVE PERSPECTIVES:
-  Strategist: Long-term planning and high-level thinking
-  Engineer: Technical implementation and systematic analysis  
-  Skeptic: Critical evaluation and assumption challenging
-  Innovator: Novel solutions and lateral thinking
-  Analyst: Data-driven insights and pattern recognition
-  Pragmatist: Practical solutions and real-world constraints
-  Synthesizer: Integration and holistic understanding

 PARAMETERS:
- thought: Your current reasoning step
- thought_number: Current number in sequence
- total_thoughts: Estimated final count (adjust as needed)
- next_thought_needed: Set to FALSE when reasoning is complete
- branch_from_thought + branch_id: Explore alternatives ()
- is_revision + revises_thought: Revise earlier reasoning ()

 OUTPUTS:
- cognitive_insights: Detected patterns and breakthroughs
- cognitive_interventions: Applied reasoning strategies with bounded activation context for why they fired now
- hypothesis_ledger: Active working hypotheses with support, contradiction, next validation steps, and bounded confidence-change explanations
- reasoning_mode: Current grounded reasoning posture (exploration, validation, revision, branching, convergence)
- recent_mode_shifts: Bounded history of recent mode transitions and why they occurred
- action_ranking: Structured next actions with primary, fallback, and do-not-do-yet guidance
- detected_biases: Cognitive biases found in reasoning
- ai_recommendations: Suggested next steps
- metacognitive_awareness: Heuristic self-reflection score (0-1)
- breakthrough_likelihood: Heuristic novelty potential score (0-1)`,
  inputSchema: THOUGHT_DATA_JSON_SCHEMA as any, // SDK expects unknown JSON schema shape
  annotations: {
    title: 'Map. Think. Do.',
    readOnlyHint: true,
  },
};

// Deprecated export retained for compatibility with existing internal imports/tests.
export const CODE_REASONING_TOOL = PLAN_AUDIT_MAP_TOOL;

export const PLAN_AUDIT_MAP_FEEDBACK_TOOL_NAME = 'plan-audit-map-feedback';

export const PLAN_AUDIT_MAP_FEEDBACK_TOOL: Tool = {
  name: PLAN_AUDIT_MAP_FEEDBACK_TOOL_NAME,
  description: ` Report the real-world outcome of a Map. Think. Do. reasoning session so the
server can learn from it — confidence calibration, strategy selection, and pattern learning all
depend on this signal.

Call this once you know how a prior reasoning session actually turned out, using the session_id
returned in that session's plan-audit-map responses.

 PARAMETERS:
- session_id: The session_id returned by a prior plan-audit-map response
- outcome: 'success' | 'failure' | 'partial'
- score: How well it turned out, 0.0 (worst) to 1.0 (best)
- comment: Optional short note on what happened`,
  inputSchema: FEEDBACK_DATA_JSON_SCHEMA as any, // SDK expects unknown JSON schema shape
  annotations: {
    title: 'Map. Think. Do. — Feedback',
    readOnlyHint: false,
  },
};

function isSupportedToolName(name: string): boolean {
  return name === PLAN_AUDIT_MAP_TOOL_NAME || name === LEGACY_TOOL_NAME;
}

function summarizePromptArgsForLogging(args: Record<string, string>): {
  argCount: number;
  argNames: string[];
} {
  const argNames = Object.keys(args).sort().slice(0, 10);
  return {
    argCount: Object.keys(args).length,
    argNames,
  };
}

/**
 * Distinguish caller-input errors (missing/invalid args, unknown prompt) from
 * genuine internal errors. Client errors describe the request — not server
 * internals or secrets — so it is safe and useful to surface their message.
 */
function isPromptClientError(message: string): boolean {
  return (
    message.startsWith('Prompt not found:') ||
    message.startsWith('Validation errors:') ||
    message.startsWith('Invalid prompt arguments:') ||
    message.startsWith('Invalid value for argument')
  );
}

/* -------------------------------------------------------------------------- */
/*                        STDIO TRANSPORT WITH FILTERING                      */
/* -------------------------------------------------------------------------- */

class FilteredStdioServerTransport extends StdioServerTransport {
  private static readonly MAX_INPUT_BUFFER_BYTES = 1024 * 1024;

  private originalStdoutWrite: typeof process.stdout.write;
  private directStdoutWrite: typeof process.stdout.write;
  private isTransportClosed: boolean = false;
  private transportError: Error | null = null;
  private started = false;
  private inputBuffer = '';
  private readonly handleStdoutError = (err: Error): void => {
    console.error(' Stdout error:', err.message);
    this.transportError = err;
    if (err.message.includes('EPIPE') || err.message.includes('ECONNRESET')) {
      this.isTransportClosed = true;
    }
  };
  private readonly handleStdinError = (err: Error): void => {
    this.transportError = err;
    if (err.message.includes('EPIPE') || err.message.includes('ECONNRESET')) {
      this.isTransportClosed = true;
    }
    this.onerror?.(err);
  };
  private readonly handleStdinData = (chunk: Buffer): void => {
    this.inputBuffer += chunk.toString('utf8');

    if (
      Buffer.byteLength(this.inputBuffer, 'utf8') >
      FilteredStdioServerTransport.MAX_INPUT_BUFFER_BYTES
    ) {
      this.inputBuffer = '';
      void this.sendProtocolError(ErrorCode.ParseError, 'Parse error');
      return;
    }

    this.processInputBuffer();
  };

  constructor() {
    super();

    // Store the original implementation before making any changes
    this.originalStdoutWrite = process.stdout.write;

    // Create a bound version that preserves the original context
    const boundOriginalWrite = this.originalStdoutWrite.bind(process.stdout);
    this.directStdoutWrite = boundOriginalWrite;

    // Override with a new function that handles errors gracefully
    process.stdout.write = ((data: string | Uint8Array): boolean => {
      // Check if transport is closed before attempting to write
      if (this.isTransportClosed) {
        console.error(' Attempted to write to closed transport, ignoring');
        return false;
      }

      try {
        if (typeof data === 'string') {
          const s = data.trimStart();
          if (s.startsWith('{') || s.startsWith('[')) {
            // Call the bound function directly to avoid circular reference
            return boundOriginalWrite(data);
          }
          // Silent handling of non-JSON strings
          return true;
        }
        // For non-string data, use the original implementation
        return boundOriginalWrite(data);
      } catch (err) {
        // Handle EPIPE, ECONNRESET, and other transport errors
        const error = err as Error;
        if (
          error.message.includes('EPIPE') ||
          error.message.includes('ECONNRESET') ||
          error.message.includes('closed')
        ) {
          console.error(' Transport connection lost:', error.message);
          this.transportError = error;
          this.isTransportClosed = true;
          return false;
        }
        // Re-throw non-transport errors
        throw error;
      }
    }) as any;

    // Handle process stdout errors
    process.stdout.on('error', this.handleStdoutError);
  }

  async start(): Promise<void> {
    if (this.started) {
      throw new Error(
        'FilteredStdioServerTransport already started! Server.connect() should only be called once.'
      );
    }

    this.started = true;
    process.stdin.on('data', this.handleStdinData);
    process.stdin.on('error', this.handleStdinError);
    // FIX: the base class's stdin 'end'/'close' handling was silently
    // dropped when start() was overridden, so when the MCP client closed
    // stdin the server never noticed and the process leaked (one zombie
    // node.exe per client disconnect).  Per the MCP stdio spec, EOF on
    // stdin means the client is gone: shut down.
    process.stdin.on('end', this.handleStdinEnd);
    process.stdin.on('close', this.handleStdinEnd);
  }

  private readonly handleStdinEnd = (): void => {
    if (this.isTransportClosed) {
      return;
    }
    this.isTransportClosed = true;
    try {
      this.onclose?.();
    } catch {
      // never let a listener error block exit
    }
    // Watchdog: force exit even if some other handle keeps the event loop
    // alive.  1.5s gives pending writes a chance to flush.
    setTimeout(() => process.exit(0), 1500);
  }

  private processInputBuffer(): void {
    while (true) {
      const newlineIndex = this.inputBuffer.indexOf('\n');
      if (newlineIndex === -1) {
        return;
      }

      const line = this.inputBuffer.slice(0, newlineIndex).replace(/\r$/, '');
      this.inputBuffer = this.inputBuffer.slice(newlineIndex + 1);

      if (line.trim().length === 0) {
        continue;
      }

      this.processInputLine(line);
    }
  }

  private processInputLine(line: string): void {
    try {
      const parsed = JSON.parse(line);
      const message = JSONRPCMessageSchema.parse(parsed);
      this.onmessage?.(message);
    } catch (error) {
      void this.handleInputError(error as Error);
    }
  }

  private async handleInputError(error: Error): Promise<void> {
    if (error instanceof SyntaxError) {
      await this.sendProtocolError(ErrorCode.ParseError, 'Parse error');
      return;
    }

    if (error instanceof ZodError) {
      await this.sendProtocolError(ErrorCode.InvalidRequest, 'Invalid Request');
      return;
    }

    this.onerror?.(error);
  }

  private async sendProtocolError(code: ErrorCode, message: string): Promise<void> {
    if (this.isTransportClosed) {
      return;
    }

    try {
      this.directStdoutWrite(
        `${JSON.stringify({ jsonrpc: '2.0', id: null, error: { code, message } })}\n`
      );
    } catch (error) {
      const transportError = error as Error;
      this.transportError = transportError;
      this.isTransportClosed = true;
      this.onerror?.(transportError);
    }
  }

  // Check if transport is available
  public isReady(): boolean {
    return !this.isTransportClosed && !this.transportError;
  }

  // Get transport error if any
  public getError(): Error | null {
    return this.transportError;
  }

  // Add cleanup to restore the original when the transport is closed
  async close(): Promise<void> {
    console.error(' Closing FilteredStdioServerTransport');
    this.isTransportClosed = true;
    this.started = false;
    this.inputBuffer = '';

    // Restore the original stdout.write before closing
    if (this.originalStdoutWrite) {
      process.stdout.write = this.originalStdoutWrite;
    }

    process.stdin.off('data', this.handleStdinData);
    process.stdin.off('error', this.handleStdinError);
    process.stdin.off('end', this.handleStdinEnd);
    process.stdin.off('close', this.handleStdinEnd);
    if (process.stdin.listenerCount('data') === 0) {
      process.stdin.pause();
    }

    // Remove error listeners
    process.stdout.off('error', this.handleStdoutError);

    // Call the parent class's close method only if not already closed
    try {
      await super.close();
    } catch (err) {
      console.error(' Error closing parent transport:', err);
    }
  }
}

/* -------------------------------------------------------------------------- */
/*                              SERVER IMPLEMENTATION                         */
/* -------------------------------------------------------------------------- */

class CodeReasoningServer {
  /** Bounded ring of the most-recent thoughts (capped at MAX_THOUGHTS). */
  private readonly thoughtHistory: ValidatedThoughtData[] = [];
  /** Cached count of revision thoughts — avoids O(N) .filter() scan. */
  private revisionCount = 0;
  private readonly branches = new Map<string, ValidatedThoughtData[]>();
  private cognitiveOrchestrator!: CognitiveOrchestrator;
  public readonly memoryStore: SQLiteStore;
  private readonly biasDetector: BiasDetector;
  private mcpManager!: MCPIntegrationManager;
  private currentSessionId: string;
  private readonly sessionStartedAt: Date;
  private readonly thoughtMutex = new Mutex();
  // Retention: run an outcome-weighted prune every N processed thoughts.
  private static readonly PRUNE_CHECK_EVERY = 100;
  private thoughtsSincePrune = 0;

  /**
   * Get the cognitive orchestrator instance for cleanup
   */
  public getCognitiveOrchestrator(): CognitiveOrchestrator {
    return this.cognitiveOrchestrator;
  }

  constructor(private readonly cfg: Readonly<MapThinkDoConfig>) {
    // Initialize persistent SQLite memory store
    // FIX: honour PLAN_AUDIT_MAP_HOME / PLAN_AUDIT_MAP_DB so the Node server and
    // the Python desk stack (taskbar bar, SQL viewer, launcher wire tap —
    // all of which honour these vars) share ONE database.  The previous
    // hardcode silently split conversations across two memory.db files
    // whenever an env override was set.
    const mtdHome = process.env.PLAN_AUDIT_MAP_HOME || process.env.PLAN_AUDIT_MAP_CONFIG_DIR || '';
    const mtdDb = process.env.PLAN_AUDIT_MAP_DB || process.env.PLAN_AUDIT_MAP_MEMORY_DB || '';
    const dbPath = mtdDb
      ? path.resolve(mtdDb)
      : mtdHome
        ? path.join(path.resolve(mtdHome), 'memory.db')
        : path.join(os.homedir(), '.plan-audit-map', 'memory.db');
    this.memoryStore = new SQLiteStore(dbPath);

    // Initialize bias detector with learning
    this.biasDetector = new BiasDetector(this.memoryStore);

    // Cognitive orchestrator will be initialized via initialize() method

    // Generate session ID for this reasoning session
    this.sessionStartedAt = new Date();
    this.currentSessionId = this.generateSessionId();

    console.error(' Map. Think. Do. - Cognitive reasoning system initialized', {
      cfg,
      sessionId: this.currentSessionId,
      dbPath,
      capabilities: 'SQLITE_PERSISTENCE + BIAS_DETECTION + OUTCOME_TRACKING + MCP_INTEGRATION',
    });
  }

  /**
   * Get MCP Integration Manager for external tool access
   */
  public getMCPManager(): MCPIntegrationManager {
    return this.mcpManager;
  }

  /**
   * Initialize the cognitive orchestrator with dependency injection
   */
  async initialize(): Promise<void> {
    // Initialize cognitive orchestrator with dependency injection.
    // Share the server's SQLiteStore so the orchestrator persists to the same
    // durable database (single source of truth) rather than an in-memory store.
    this.cognitiveOrchestrator = await createCognitiveOrchestrator({
      memoryStore: this.memoryStore,
      config: {
        max_concurrent_interventions: 5,
        intervention_cooldown_ms: 500,
        adaptive_plugin_selection: true,
        learning_rate: 0.15,
        memory_integration_enabled: true,
        pattern_recognition_threshold: 0.6,
        adaptive_learning_enabled: true,
        emergence_detection_enabled: true,
        breakthrough_detection_sensitivity: 0.75,
        insight_cultivation_enabled: true,
        performance_monitoring_enabled: true,
        self_optimization_enabled: true,
        cognitive_load_balancing: true,
      },
    });

    // Initialize MCP Integration Manager for external tool access
    this.mcpManager = new MCPIntegrationManager(this.memoryStore, {
      autoConnect: true,
      watchPlugins: true,
      healthCheckInterval: 30000,
    });

    try {
      await this.mcpManager.initialize();
      const status = this.mcpManager.getStatus();
      console.error(' MCP Integration Manager initialized', {
        connectedServers: status.connectedServers,
        availableTools: status.totalTools,
        loadedPlugins: status.loadedPlugins,
      });
    } catch (err) {
      console.error(' MCP Integration Manager initialization failed (non-fatal):', err);
    }

    console.error(' Cognitive orchestrator initialized', {
      sessionId: this.currentSessionId,
      capabilities: 'MULTI_PERSONA + BIAS_DETECTION + EXTERNAL_TOOLS',
    });

    // Bound durable memory growth across restarts: prune low-signal aged
    // thoughts at startup (aggregates and high-signal thoughts are retained).
    const prunedAtStartup = this.memoryStore.pruneThoughts();
    if (prunedAtStartup > 0) {
      console.error(` Pruned ${prunedAtStartup} low-signal thought(s) from durable memory`);
    }
  }

  /**
   * Generate unique session ID for reasoning sessions
   */
  private generateSessionId(): string {
    return `session_${randomUUID()}`;
  }

  /* ----------------------------- Helper Methods ---------------------------- */

  private async formatThoughtSecure(t: ValidatedThoughtData): Promise<string> {
    const {
      thought_number,
      total_thoughts,
      thought,
      is_revision,
      revises_thought,
      branch_id,
      branch_from_thought,
    } = t;

    const header = is_revision
      ? ` Revision ${thought_number}/${total_thoughts} (of ${revises_thought})`
      : branch_id
        ? ` Branch ${thought_number}/${total_thoughts} (from ${branch_from_thought}, id:${branch_id})`
        : ` Thought ${thought_number}/${total_thoughts}`;

    // Log the thought content securely
    await secureLogger.logThought(thought, 'CodeReasoningServer', 'formatThoughtSecure', {
      thought_number,
      total_thoughts,
      is_revision: is_revision || false,
      revises_thought,
      branch_id,
      branch_from_thought,
    });

    // For console output, use header only (thought content is logged securely above)
    return `\n${header}\n--- [Content logged securely] ---`;
  }

  private buildSuccess(
    t: ValidatedThoughtData,
    cognitiveResult?: {
      interventions: any[];
      insights: any[];
      cognitiveState: any;
      recommendations: string[];
      actionRanking: ActionRanking;
    },
    biasDetections?: Array<{
      bias_id: string;
      bias_name: string;
      confidence: number;
      evidence: string[];
      suggested_corrections: string[];
      severity: 'low' | 'medium' | 'high';
    }>
  ): ServerResult {
    // Get recommended external tools if MCP manager is available
    let recommendedTools: Array<{ name: string; source: string; score: number }> = [];
    try {
      if (this.mcpManager) {
        recommendedTools = this.mcpManager.recommendTools(t.thought, 3);
      }
    } catch {
      // Non-fatal: MCP recommendations are optional
    }

    const cs = cognitiveResult?.cognitiveState;
    const formattedState = formatObjectNumbers(cs);

    const payload = {
      status: 'processed',
      session_id: this.currentSessionId,
      thought_number: t.thought_number,
      total_thoughts: t.total_thoughts,
      next_thought_needed: t.next_thought_needed,
      branches: Array.from(this.branches.keys()),
      thought_history_length: this.thoughtHistory.length,
      cognitive_insights: cognitiveResult?.insights || [],
      cognitive_interventions: cognitiveResult?.interventions || [],
      cognitive_state: formattedState,
      hypothesis_ledger: cs?.hypothesis_ledger || [],
      reasoning_mode: cs?.reasoning_mode || 'exploration',
      recent_mode_shifts: cs?.recent_mode_shifts || [],
      action_ranking: cognitiveResult?.actionRanking || null,
      ai_recommendations: cognitiveResult?.recommendations || [],
      detected_biases:
        biasDetections?.map(b => ({
          bias: b.bias_name,
          confidence: b.confidence,
          severity: b.severity,
          corrections: b.suggested_corrections,
        })) || [],
      recommended_external_tools: recommendedTools,
      metacognitive_awareness: (formattedState as any)?.metacognitive_awareness ?? '0.00',
      creative_pressure: (formattedState as any)?.creative_pressure ?? '0.00',
      breakthrough_likelihood: (formattedState as any)?.breakthrough_likelihood ?? '0.00',
      cognitive_flexibility: (formattedState as any)?.cognitive_flexibility ?? '0.00',
      insight_potential: (formattedState as any)?.insight_potential ?? '0.00',
    } as const;

    return { content: [{ type: 'text', text: JSON.stringify(payload, null, 2) }], isError: false };
  }

  /**
   * Build tool error response with contextual guidance for AI recovery
   */
  private buildToolError(message: string): ServerResult {
    return {
      content: [{ type: 'text', text: message }],
      isError: true,
    };
  }

  /**
   * Build contextual validation guidance from Zod errors
   */
  private buildValidationGuidance(errors: any[]): string {
    const guidanceMap: Record<string, string> = {
      thought:
        'Your thought content is invalid. Ensure it contains meaningful text between 1-20000 characters. Empty thoughts or extremely long thoughts are not allowed.',
      thought_number:
        'The thought_number must be a positive integer. Start with 1 for your first thought and increment sequentially.',
      total_thoughts:
        'The total_thoughts must be a positive integer representing your estimated final thought count. You can adjust this as you progress.',
      next_thought_needed:
        'The next_thought_needed field must be true or false. Set to false when you complete your reasoning.',
      revises_thought:
        'When using is_revision=true, you must specify which thought number you are revising with revises_thought.',
      branch_from_thought:
        'When branching, specify which existing thought you are branching from using a valid thought number.',
      branch_id:
        'When branching, provide a unique branch_id string to identify this exploration path.',
    };

    const guidance = errors
      .map(error => {
        const field = error.path.join('.');
        const customGuidance = guidanceMap[field];
        if (customGuidance) {
          return `${field}: ${customGuidance}`;
        }
        return `${field}: ${error.message}`;
      })
      .join('\n\n');

    return `Validation errors found:\n\n${guidance}\n\nPlease correct these issues and try again. Each field serves a specific purpose in the reasoning process.`;
  }

  /* ------------------------------ Main Handler ----------------------------- */

  public async processThought(input: unknown): Promise<ServerResult> {
    const t0 = performance.now();

    try {
      const data = validateThoughtData(input);

      // Sanity limits with contextual guidance for AI recovery
      if (data.thought_number > MAX_THOUGHTS) {
        return this.buildToolError(
          `Thought limit reached (${MAX_THOUGHTS}). Consider breaking complex problems into separate reasoning sessions, or complete your analysis with fewer thoughts. Most problems can be solved effectively in 10-15 thoughts. You can start a new reasoning session to continue if needed.`
        );
      }
      if (data.branch_from_thought && data.branch_from_thought > this.thoughtHistory.length) {
        return this.buildToolError(
          `Invalid branch reference: thought ${data.branch_from_thought} doesn't exist. You currently have ${this.thoughtHistory.length} thoughts in your history. Use a valid thought number between 1-${this.thoughtHistory.length} for branching. To explore alternatives, branch from an existing thought that represents a decision point.`
        );
      }

      console.error(' Engaging cognitive orchestrator for structured reasoning...');

      //  REAL Bias Detection - analyze thought for cognitive biases
      const biasDetections = await this.biasDetector.detectBiases(data.thought, {
        confidence: this.estimateInitialConfidence(data),
        thought_number: data.thought_number,
        total_thoughts: data.total_thoughts,
        domain: this.inferDomain(data),
        previous_thoughts: this.thoughtHistory
          .slice(-MAX_PREVIOUS_THOUGHTS_CONTEXT)
          .map(t => t.thought),
      });

      // Log detected biases
      if (biasDetections.length > 0) {
        console.error(
          ' Cognitive biases detected:',
          biasDetections.map(b => ({
            bias: b.bias_name,
            confidence: b.confidence.toFixed(2),
            severity: b.severity,
          }))
        );
      }

      const cognitiveResult = await this.cognitiveOrchestrator.processThought(data, {
        id: this.currentSessionId,
        objective: this.inferObjective(data),
        domain: this.inferDomain(data),
        start_time: this.sessionStartedAt,
        goal_achieved: false,
        confidence_level: 0.5,
        total_thoughts: data.total_thoughts,
        revision_count: this.revisionCount,
        branch_count: this.branches.size,
      });

      // Thought persistence is owned by the cognitive orchestrator, which writes
      // the enriched thought to the shared SQLiteStore (single source of truth)
      // under this.currentSessionId. See initialize().

      // Periodically bound durable memory growth (outcome-weighted retention).
      if (++this.thoughtsSincePrune >= CodeReasoningServer.PRUNE_CHECK_EVERY) {
        this.thoughtsSincePrune = 0;
        const pruned = this.memoryStore.pruneThoughts();
        if (pruned > 0) {
          console.error(` Pruned ${pruned} low-signal thought(s) from durable memory`);
        }
      }

      // Stats & storage -----------------------------------------------------
      // Use mutex to prevent race conditions in shared state mutations
      await this.thoughtMutex.withLock(async () => {
        // Bounded history: evict the oldest entry when at capacity so that the
        // array never grows beyond MAX_THOUGHTS elements and the evicted entry's
        // contribution to revisionCount is subtracted.
        if (this.thoughtHistory.length >= MAX_THOUGHTS) {
          const evicted = this.thoughtHistory.shift();
          if (evicted?.is_revision) {
            this.revisionCount = Math.max(0, this.revisionCount - 1);
          }
        }
        this.thoughtHistory.push(data);
        if (data.is_revision) {
          this.revisionCount++;
        }
        if (data.branch_id) {
          const arr = this.branches.get(data.branch_id) ?? [];
          arr.push(data);
          this.branches.set(data.branch_id, arr);
        }
      });

      // Persist the session row so the sessions table is the single source of
      // truth for session-level data (and the outcomes->sessions FK is satisfied
      // natively). Best-effort — runs after stats so counts are current.
      await this.persistCurrentSession(data, cognitiveResult);

      // Enhanced logging with cognitive insights (secure)
      console.error(await this.formatThoughtSecure(data));
      console.error(' Cognitive Summary:', {
        metacognitive_awareness: cognitiveResult.cognitiveState.metacognitive_awareness,
        creative_pressure: cognitiveResult.cognitiveState.creative_pressure,
        breakthrough_likelihood: cognitiveResult.cognitiveState.breakthrough_likelihood,
        insights_detected: cognitiveResult.insights.length,
        interventions_applied: cognitiveResult.interventions.length,
        recommendations_generated: cognitiveResult.recommendations.length,
      });

      console.error(' Cognitive processing complete', {
        num: data.thought_number,
        cognitive_efficiency: cognitiveResult.cognitiveState.task_efficiency,
        biases_detected: biasDetections.length,
        elapsedMs: +(performance.now() - t0).toFixed(1),
      });

      return this.buildSuccess(data, cognitiveResult, biasDetections);
    } catch (err) {
      const e = err as Error;
      console.error(' Cognitive processing error', {
        err: e.message,
        elapsedMs: +(performance.now() - t0).toFixed(1),
      });

      // Handle validation errors with contextual guidance
      if (err instanceof ZodError) {
        if (this.cfg.debug) console.error(err.errors);

        const validationGuidance = this.buildValidationGuidance(err.errors);
        return this.buildToolError(validationGuidance);
      }

      // Handle MCP protocol errors (pass through - these are genuine protocol issues)
      if (err instanceof McpError) {
        throw err;
      }

      // Handle unknown errors with smart recovery guidance
      return this.buildToolError(GENERIC_PROCESSING_ERROR_MESSAGE);
    }
  }

  /**
   * Record outcome feedback for a prior reasoning session, closing the learning
   * loop (confidence calibration, state calibration, pattern learning).
   */
  public async processFeedback(input: unknown): Promise<ServerResult> {
    try {
      const data = validateFeedbackData(input);

      // Persist the outcome to the durable SQLite store so it feeds confidence
      // calibration (read back via getCalibratedConfidence) and learning patterns.
      const outcomePersisted = await this.recordOutcomeForSession(data);

      // Apply the feedback signal to the live cognitive state.
      this.cognitiveOrchestrator.recordReasoningOutcome({
        sessionId: data.session_id,
        outcome: data.outcome,
        outcomeScore: data.score,
      });

      const payload = {
        status: 'feedback_recorded',
        session_id: data.session_id,
        outcome: data.outcome,
        score: data.score,
        outcome_persisted: outcomePersisted,
      } as const;

      return {
        content: [{ type: 'text', text: JSON.stringify(payload, null, 2) }],
        isError: false,
      };
    } catch (err) {
      if (err instanceof ZodError) {
        return this.buildToolError(this.buildValidationGuidance(err.errors));
      }
      if (err instanceof McpError) {
        throw err;
      }
      return this.buildToolError(GENERIC_PROCESSING_ERROR_MESSAGE);
    }
  }

  /**
   * Persist an outcome against the most recent stored thought of the given
   * session, driving confidence calibration and learning-pattern updates.
   * Returns whether an outcome row was written. Best-effort: never throws.
   */
  private async recordOutcomeForSession(data: ValidatedFeedbackData): Promise<boolean> {
    try {
      const recent = await this.memoryStore.queryThoughts({
        session_ids: [data.session_id],
        limit: 1,
        sort_by: 'timestamp',
        sort_order: 'desc',
      });
      const latest = recent[0];
      if (!latest) {
        return false;
      }

      // The outcomes table references sessions(id), but the server persists
      // thoughts without a session row — backfill it so the FK is satisfied.
      await this.ensureSessionPersisted(data.session_id, latest);

      this.memoryStore.recordOutcome({
        id: randomUUID(),
        thought_id: latest.id,
        session_id: data.session_id,
        prediction: latest.objective ?? '',
        predicted_confidence: latest.confidence ?? 0.5,
        actual_outcome: data.outcome,
        outcome_score: data.score,
        feedback: data.comment,
        recorded_at: new Date(),
        domain: latest.domain,
      });
      return true;
    } catch (err) {
      console.error('Failed to persist reasoning outcome', {
        sessionId: data.session_id,
        error: (err as Error).message,
      });
      return false;
    }
  }

  /**
   * Ensure a session row exists for the given id (the outcomes table has a
   * foreign key to sessions). Creates a minimal row from the latest thought if
   * absent; never overwrites an existing session.
   */
  /**
   * Upsert the current reasoning session so the sessions table is the single
   * source of truth for session-level data and the outcomes->sessions FK is
   * satisfied natively. Server-owned fields (counts, confidence) are refreshed
   * each thought; objective/domain/start_time are set once; any enrichment on an
   * existing row is preserved by merging. Best-effort: logged, never throws.
   */
  private async persistCurrentSession(
    data: ValidatedThoughtData,
    cognitiveResult: { cognitiveState: { confidence_trajectory: number[] } }
  ): Promise<void> {
    try {
      const existing = await this.memoryStore.getSession(this.currentSessionId);
      const trajectory = cognitiveResult.cognitiveState.confidence_trajectory;
      const confidenceLevel = trajectory.length ? trajectory[trajectory.length - 1] : 0.5;

      const base: ReasoningSession = existing ?? {
        id: this.currentSessionId,
        start_time: this.sessionStartedAt,
        objective: this.inferObjective(data),
        goal_achieved: false,
        confidence_level: confidenceLevel,
        total_thoughts: 0,
        revision_count: 0,
        branch_count: 0,
      };

      await this.memoryStore.storeSession({
        ...base,
        id: this.currentSessionId,
        start_time: existing?.start_time ?? this.sessionStartedAt,
        objective: existing?.objective ?? this.inferObjective(data),
        domain: existing?.domain ?? this.inferDomain(data),
        confidence_level: confidenceLevel,
        total_thoughts: this.thoughtHistory.length,
        revision_count: this.revisionCount,
        branch_count: this.branches.size,
      });
    } catch (err) {
      console.error('Failed to persist session', {
        sessionId: this.currentSessionId,
        error: (err as Error).message,
      });
    }
  }

  private async ensureSessionPersisted(sessionId: string, latest: StoredThought): Promise<void> {
    const existing = await this.memoryStore.getSession(sessionId);
    if (existing) {
      return;
    }

    await this.memoryStore.storeSession({
      id: sessionId,
      start_time: latest.timestamp ?? new Date(),
      objective: latest.objective ?? 'Reasoning session',
      domain: latest.domain,
      goal_achieved: false,
      confidence_level: latest.confidence ?? 0.5,
      total_thoughts: latest.total_thoughts ?? 0,
      revision_count: 0,
      branch_count: 0,
    });
  }

  /**
   * Helper methods for cognitive processing
   */
  private inferObjective(data: ValidatedThoughtData): string {
    // Simple objective inference based on thought content
    if (
      data.thought.toLowerCase().includes('bug') ||
      data.thought.toLowerCase().includes('error')
    ) {
      return 'Debug and fix issues';
    }
    if (
      data.thought.toLowerCase().includes('implement') ||
      data.thought.toLowerCase().includes('build')
    ) {
      return 'Implementation and development';
    }
    if (
      data.thought.toLowerCase().includes('design') ||
      data.thought.toLowerCase().includes('architecture')
    ) {
      return 'System design and architecture';
    }
    return 'General problem solving';
  }

  private inferDomain(data: ValidatedThoughtData): string {
    const thought = data.thought.toLowerCase();
    if (thought.includes('code') || thought.includes('function') || thought.includes('class')) {
      return 'software_development';
    }
    if (
      thought.includes('algorithm') ||
      thought.includes('performance') ||
      thought.includes('optimization')
    ) {
      return 'algorithms';
    }
    if (thought.includes('design') || thought.includes('ui') || thought.includes('ux')) {
      return 'design';
    }
    if (thought.includes('database') || thought.includes('data') || thought.includes('storage')) {
      return 'data_management';
    }
    return 'general';
  }

  /**
   * Estimate initial confidence based on thought content
   * Uses REAL calibration from SQLiteStore historical data
   */
  private estimateInitialConfidence(data: ValidatedThoughtData): number {
    const thought = data.thought.toLowerCase();
    let rawConfidence = 0.5;

    // High confidence indicators
    if (thought.includes('definitely') || thought.includes('certainly')) rawConfidence += 0.3;
    if (thought.includes('clearly') || thought.includes('obviously')) rawConfidence += 0.2;
    if (thought.includes('confident') || thought.includes('sure')) rawConfidence += 0.2;

    // Low confidence indicators
    if (thought.includes('maybe') || thought.includes('perhaps')) rawConfidence -= 0.2;
    if (thought.includes('uncertain') || thought.includes('unsure')) rawConfidence -= 0.3;
    if (thought.includes('might') || thought.includes('could be')) rawConfidence -= 0.1;

    // Revision indicates some uncertainty
    if (data.is_revision) rawConfidence -= 0.1;

    // Clamp raw confidence
    rawConfidence = Math.min(1, Math.max(0, rawConfidence));

    // Apply REAL calibration from SQLiteStore based on historical accuracy
    const domain = this.inferDomain(data);
    const calibratedConfidence = this.memoryStore.getCalibratedConfidence(rawConfidence, domain);

    console.error(' Confidence calibration:', {
      raw: rawConfidence.toFixed(2),
      calibrated: calibratedConfidence.toFixed(2),
      domain,
    });

    return calibratedConfidence;
  }

  /**
   * Cleanup resources
   */
  async destroy(): Promise<void> {
    // Clear data structures
    this.thoughtHistory.length = 0;
    this.revisionCount = 0;
    this.branches.clear();

    // Cleanup MCP Integration Manager
    try {
      if (this.mcpManager) {
        await this.mcpManager.destroy();
        console.error(' MCP Integration Manager closed');
      }
    } catch (err) {
      console.error(' Error closing MCP manager:', err);
    }

    // Close the SQLite memory store properly
    try {
      await this.memoryStore.close();
      console.error(' SQLite memory store closed');
    } catch (err) {
      console.error(' Error closing memory store:', err);
    }

    // The cognitive orchestrator cleanup is handled separately
  }
}

/* -------------------------------------------------------------------------- */
/*                                BOOTSTRAP                                   */
/* -------------------------------------------------------------------------- */

const DASHBOARD_HTML = `<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Map. Think. Do. — Cognitive Dashboard</title>
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;700&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg: #030303;
            --card: rgba(18, 18, 18, 0.7);
            --border: rgba(255, 255, 255, 0.08);
            --text: #f3f4f6;
            --text-muted: #9ca3af;
            --accent: #a855f7;
            --accent-glow: rgba(168, 85, 247, 0.15);
            --success: #10b981;
        }
        * { box-sizing: border-box; margin: 0; padding: 0; font-family: 'Outfit', sans-serif; }
        body { background: var(--bg); color: var(--text); padding: 2rem; min-height: 100vh; display: flex; flex-direction: column; align-items: center; }
        .container { width: 100%; max-width: 1000px; }
        header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 2rem; border-bottom: 1px solid var(--border); padding-bottom: 1rem; }
        h1 { font-size: 1.8rem; font-weight: 700; letter-spacing: -0.05em; background: linear-gradient(to right, #ffffff, #a855f7); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
        .badge { background: var(--accent-glow); border: 1px solid var(--accent); color: #c084fc; padding: 0.25rem 0.75rem; border-radius: 9999px; font-size: 0.85rem; font-weight: 600; }
        .grid { display: grid; grid-template-columns: 1fr; gap: 1.5rem; }
        .card { background: var(--card); border: 1px solid var(--border); border-radius: 12px; padding: 1.5rem; backdrop-filter: blur(16px); box-shadow: 0 4px 30px rgba(0, 0, 0, 0.5); }
        .timeline { position: relative; margin-top: 1rem; padding-left: 2rem; border-left: 2px solid var(--border); }
        .thought-item { position: relative; margin-bottom: 2rem; }
        .thought-item::before { content: ''; position: absolute; left: calc(-2rem - 6px); top: 4px; width: 10px; height: 10px; border-radius: 50%; background: var(--accent); box-shadow: 0 0 8px var(--accent); }
        .thought-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.5rem; }
        .thought-number { font-weight: 600; color: var(--accent); }
        .thought-meta { font-size: 0.85rem; color: var(--text-muted); }
        .thought-content { line-height: 1.6; font-size: 1rem; color: #e5e7eb; white-space: pre-wrap; }
        .empty { text-align: center; color: var(--text-muted); padding: 3rem 0; }
        button { background: var(--accent); color: white; border: none; padding: 0.5rem 1rem; border-radius: 6px; cursor: pointer; font-weight: 600; transition: all 0.2s; }
        button:hover { opacity: 0.9; transform: translateY(-1px); }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <div>
                <h1>Map. Think. Do.</h1>
                <p style="color: var(--text-muted); font-size: 0.95rem; margin-top: 0.25rem;">Cognitive Reasoning & Reflection Console</p>
            </div>
            <div>
                <span class="badge">SSE Live</span>
            </div>
        </header>
        <div class="grid">
            <div class="card">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 1.5rem;">
                    <h2 style="font-size: 1.3rem; font-weight: 600;">Reasoning Trace</h2>
                    <button onclick="loadThoughts()">Refresh</button>
                </div>
                <div id="timeline-container">
                    <div class="empty">Loading reasoning trace...</div>
                </div>
            </div>
        </div>
    </div>
    <script>
        async function loadThoughts() {
            const container = document.getElementById('timeline-container');
            try {
                const res = await fetch('/api/thoughts');
                const data = await res.json();
                if (!data.thoughts || data.thoughts.length === 0) {
                    container.innerHTML = '<div class="empty">No thoughts stored yet. Run some tasks through the MCP server.</div>';
                    return;
                }
                let html = '<div class="timeline">';
                const sorted = data.thoughts.sort((a, b) => a.thought_number - b.thought_number);
                sorted.forEach(t => {
                    const domain = t.domain ? \` • \${t.domain}\` : '';
                    const confidence = t.confidence ? \` • Confidence: \${(t.confidence * 100).toFixed(0)}%\` : '';
                    html += \`
                        <div class="thought-item">
                            <div class="thought-header">
                                <span class="thought-number">Thought #\${t.thought_number} / \${t.total_thoughts}</span>
                                <span class="thought-meta">\${t.objective || 'General reasoning'}\${domain}\${confidence}</span>
                            </div>
                            <div class="thought-content">\${escapeHtml(t.thought)}</div>
                        </div>
                    \`;
                });
                html += '</div>';
                container.innerHTML = html;
            } catch (err) {
                container.innerHTML = \`<div class="empty" style="color: var(--error);">Error loading thoughts: \${err.message}</div>\`;
            }
        }
        function escapeHtml(str) {
            return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
        }
        loadThoughts();
    </script>
</body>
</html>
`;

// ── Monkeypatch mcp.server.sse.SseServerTransport to capture session_id ────────
let _last_session_id: string | null = null;
try {
  // @ts-ignore
  const originalStart = SSEServerTransport.prototype.start;
  // @ts-ignore
  SSEServerTransport.prototype.start = async function () {
    // @ts-ignore
    _last_session_id = this._sessionId;
    console.error(`[mcp-patch] Captured active SSE session ID: ${_last_session_id}`);
    // @ts-ignore
    return originalStart.call(this);
  };
} catch (e: any) {
  console.error('[mcp-patch] Failed to monkeypatch SSEServerTransport:', e.message);
}

// ── Integrated Tunnel Helpers ────────────────────────────────────────────────
let tunnelProcess: ChildProcess | null = null;
let tunnelUrl: string | null = null;

function isSpamLine(line: string): boolean {
  if (line.includes('\x1b') || line.includes('←[')) {
    return true;
  }
  if ((line.match(/  /g) || []).length > 15) {
    return true;
  }
  return false;
}

function startProcessAndParseUrl(cmd: string, args: string[], label: string, regex: RegExp): ChildProcess {
  console.error(`[${label}] starting: ${cmd} ${args.join(' ')}`);
  
  const proc = spawn(cmd, args, {
    detached: true,
    stdio: ['ignore', 'pipe', 'pipe']
  });
  
  proc.unref();

  let resolved = false;

  const handleOutput = (data: Buffer) => {
    const lines = data.toString('utf8').split(/\r?\n/);
    for (const line of lines) {
      const trimmed = line.trim();
      if (!trimmed) continue;
      if (isSpamLine(trimmed)) continue;
      
      console.error(`[${label}] ${trimmed}`);
      
      if (!resolved) {
        const match = trimmed.match(regex);
        if (match) {
          tunnelUrl = match[0];
          console.error(`[${label}] Discovered public tunnel URL: ${tunnelUrl}`);
          resolved = true;
        }
      }
    }
  };

  proc.stdout?.on('data', handleOutput);
  proc.stderr?.on('data', handleOutput);
  
  // Attach an error handler to prevent uncaughtException crash
  proc.on('error', (err) => {
    console.error(`[${label}] Process error: ${err.message}`);
  });
  
  return proc;
}

/**
 * Attempt a single tunnel provider. Resolves with the public base URL on success,
 * rejects if the process exits before printing a URL or if timeoutMs elapses.
 */
function attemptTunnel(
  provider: string,
  host: string,
  port: number,
  timeoutMs: number
): { proc: ChildProcess | null; promise: Promise<string> } {
  // Reset the shared global so we start fresh
  tunnelUrl = null;
  
  let proc: ChildProcess | null = null;
  try {
    proc = startTunnel(provider, host, port);
  } catch (err: any) {
    return { proc: null, promise: Promise.reject(new Error(`[${provider}] Spawn failed: ${err.message}`)) };
  }

  const promise = new Promise<string>((resolve, reject) => {
    if (!proc) {
      reject(new Error(`[${provider}] Spawn returned null process`));
      return;
    }

    const timer = setTimeout(() => {
      reject(new Error(`[${provider}] Timeout after ${timeoutMs / 1000}s — no URL received`));
    }, timeoutMs);

    // Poll tunnelUrl (set by startProcessAndParseUrl's output handler)
    const poll = setInterval(() => {
      if (tunnelUrl) {
        clearTimeout(timer);
        clearInterval(poll);
        resolve(tunnelUrl);
      }
    }, 300);

    // If the process dies before we get a URL, fail fast
    proc.on('exit', (code) => {
      if (!tunnelUrl) {
        clearTimeout(timer);
        clearInterval(poll);
        reject(new Error(`[${provider}] Process exited (code ${code}) before URL was received`));
      }
    });

    proc.on('error', (err) => {
      if (!tunnelUrl) {
        clearTimeout(timer);
        clearInterval(poll);
        reject(new Error(`[${provider}] Process error: ${err.message}`));
      }
    });
  });

  return { proc, promise };
}

function killTunnelProc(proc: ChildProcess | null) {
  if (!proc) return;
  try {
    if (process.platform === 'win32') {
      spawn('taskkill', ['/F', '/T', '/PID', proc.pid!.toString()]);
    } else {
      proc.kill();
    }
  } catch (_) {}
}

function getNgrokPath(): string {
  const userHome = process.env.USERPROFILE || os.homedir();
  const candidates = [
    process.env.NGROK_PATH,
    path.join(process.cwd(), 'ngrok.exe'),
    path.join(process.cwd(), 'ngrok'),
    path.join(userHome, 'AppData', 'Local', 'ngrok', 'ngrok.exe'),
    'ngrok.exe',
    'ngrok'
  ].filter(Boolean) as string[];

  for (const candidate of candidates) {
    try {
      if (path.isAbsolute(candidate) || candidate.startsWith('.') || candidate.includes('/') || candidate.includes('\\')) {
        if (fs.existsSync(candidate)) {
          return candidate;
        }
        continue;
      }
      const result = execSync(`"${candidate}" --version`, { encoding: 'utf8', stdio: 'pipe' });
      if (result.includes('ngrok')) {
        return candidate;
      }
    } catch (e) {}
  }
  return process.platform === 'win32' ? 'ngrok.exe' : 'ngrok';
}

function startTunnel(provider: string, host: string, port: number, explicitNgrok?: string): ChildProcess {
  console.error(`[plan-audit-map] Setting up integrated remote secure tunnel using ${provider}...`);
  
  if (provider === 'ngrok') {
    const ngrokBin = explicitNgrok || getNgrokPath();
    const args = ['http', `http://${host}:${port}`, '--log=stdout', '--log-format=logfmt'];
    const proc = spawn(ngrokBin, args, { detached: true, stdio: ['ignore', 'pipe', 'pipe'] });
    proc.unref();
    
    const handleOutput = (data: Buffer) => {
      const lines = data.toString('utf8').split(/\r?\n/);
      for (const line of lines) {
        console.error(`[ngrok] ${line.trim()}`);
      }
    };
    proc.stdout?.on('data', handleOutput);
    proc.stderr?.on('data', handleOutput);
    
    // Safety error handler to prevent uncaughtException crash
    proc.on('error', (err) => {
      console.error(`[ngrok] Process error: ${err.message}`);
    });
    
    return proc;
  }
  
  if (provider === 'pinggy') {
    // Port 443 SSH — bypasses port-22 blocks, zero install, free tier
    const args = [
      '-o', 'StrictHostKeyChecking=no',
      '-o', 'ServerAliveInterval=30',
      '-o', 'ExitOnForwardFailure=yes',
      '-p', '443',
      '-R', `0:localhost:${port}`,
      'free.pinggy.io'
    ];
    return startProcessAndParseUrl('ssh', args, 'pinggy', /https:\/\/[a-zA-Z0-9.-]+\.pinggy\.link/);
  }
  
  if (provider === 'localtunnel') {
    const args = ['localtunnel', '--port', port.toString(), '--host', `http://${host}`];
    return startProcessAndParseUrl('npx', args, 'localtunnel', /https:\/\/[a-zA-Z0-9-]+\.localtunnel\.me/);
  }
  
  if (provider === 'localhostrun') {
    // Use dedicated planauditmap key for authenticated stable tunnel (better rate limits than nokey@)
    const keyPath = `${process.env.USERPROFILE || process.env.HOME}\\.ssh\\id_ed25519_planauditmap`;
    const args = [
      '-o', 'StrictHostKeyChecking=no',
      '-o', 'ServerAliveInterval=30',
      '-o', 'ExitOnForwardFailure=yes',
      '-i', keyPath,
      '-R', `80:${host}:${port}`,
      'localhost.run'
    ];
    return startProcessAndParseUrl('ssh', args, 'localhostrun', /https:\/\/[a-zA-Z0-9-]+\.(?:localhost\.run|lhr\.life)/);
  }
  
  if (provider === 'serveo') {
    const args = [
      '-o', 'StrictHostKeyChecking=no',
      '-o', 'ServerAliveInterval=30',
      '-R', `80:${host}:${port}`,
      'serveo.net'
    ];
    return startProcessAndParseUrl('ssh', args, 'serveo', /https:\/\/[a-zA-Z0-9-]+\.serveo\.net/);
  }
  
  throw new Error(`Unknown tunnel provider: ${provider}`);
}

function getJson(url: string): Promise<any> {
  return new Promise((resolve, reject) => {
    // @ts-ignore
    const req = http.request(url, { timeout: 2000 }, (res) => {
      let data = '';
      res.on('data', chunk => data += chunk);
      res.on('end', () => {
        try {
          resolve(JSON.parse(data));
        } catch (e) {
          reject(e);
        }
      });
    });
    req.on('error', reject);
    req.end();
  });
}

async function discoverNgrokUrl(apiBase: string, timeout = 45000): Promise<string> {
  const deadline = Date.now() + timeout;
  let lastError: any = null;
  while (Date.now() < deadline) {
    try {
      const data = await getJson(`${apiBase}/api/tunnels`);
      const tunnels = data?.tunnels || [];
      const https = tunnels.find((t: any) => t.public_url && t.public_url.startsWith('https://'));
      if (https) return https.public_url;
      const anyUrl = tunnels.find((t: any) => t.public_url);
      if (anyUrl) return anyUrl.public_url;
    } catch (e) {
      lastError = e;
    }
    await new Promise(r => setTimeout(r, 1000));
  }
  throw new Error(`ngrok did not report a public URL. Last error: ${lastError?.message}`);
}

// ── Tunnel cooldown helpers ─────────────────────────────────────────────────
// After a provider gets a URL but fails the health probe, a cooldown file
// is written so that provider is skipped for 10 minutes before retrying.

const TUNNEL_COOLDOWN_DIR = path.join(
  process.env.USERPROFILE || os.homedir(), '.plan-audit-map'
);
const TUNNEL_COOLDOWN_MS = 10 * 60 * 1000; // 10 minutes

function tunnelCooldownPath(provider: string): string {
  return path.join(TUNNEL_COOLDOWN_DIR, `tunnel_cooldown_${provider}.json`);
}

function tunnelOnCooldown(provider: string): boolean {
  try {
    const p = tunnelCooldownPath(provider);
    if (!fs.existsSync(p)) return false;
    const { ts } = JSON.parse(fs.readFileSync(p, 'utf8'));
    const remaining = TUNNEL_COOLDOWN_MS - (Date.now() - ts);
    if (remaining > 0) {
      console.error(`[tunnel-fallback] ${provider} on cooldown for ${Math.ceil(remaining / 60000)}m`);
      return true;
    }
    return false;
  } catch { return false; }
}

function tunnelSetCooldown(provider: string, reason: string) {
  try {
    fs.mkdirSync(TUNNEL_COOLDOWN_DIR, { recursive: true });
    fs.writeFileSync(tunnelCooldownPath(provider), JSON.stringify({
      ts: Date.now(), reason, date: new Date().toISOString()
    }));
    console.error(`[tunnel-fallback] ${provider} cooldown 10m: ${reason}`);
  } catch {}
}

function tunnelClearCooldown(provider: string) {
  try { fs.unlinkSync(tunnelCooldownPath(provider)); } catch {}
}

/** Probe the public /health URL. Returns true only on HTTP 200 or non-HTML content. */
function probePublicHealth(publicBase: string, timeoutMs = 8000): Promise<boolean> {
  return new Promise(resolve => {
    try {
      const opts = {
        headers: {
          'User-Agent': 'MapThinkDo-HealthProbe/1.0',
          'Accept': 'application/json,text/event-stream',
          'ngrok-skip-browser-warning': '69420'
        },
        timeout: timeoutMs
      };
      const req = https.get(`${publicBase}/health`, opts, res => {
        let data = '';
        res.on('data', chunk => data += chunk);
        res.on('end', () => {
          const isGood = (res.statusCode && res.statusCode >= 200 && res.statusCode < 300) ||
                         !data.includes('<!DOCTYPE html>');
          resolve(isGood);
        });
      });
      req.on('error', () => resolve(false));
      req.on('timeout', () => {
        req.destroy();
        resolve(false);
      });
    } catch {
      resolve(false);
    }
  });
}

function cleanupPort(port: number) {
  console.error(`[Tunnel] Cleaning up port ${port}...`);
  try {
    // PowerShell robust cleanup (handles IPv4/IPv6, various states)
    execSync(
      `powershell -NoProfile -Command "Get-NetTCPConnection -LocalPort ${port} -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }"`,
      { stdio: 'ignore' }
    );
  } catch (e) {
    // fallback to netstat/taskkill
    try {
      const out = execSync(`netstat -aon | findstr :${port}`, { encoding: 'utf8' });
      const pids = new Set(
        out.split(/\r?\n/)
          .map(l => l.trim().split(/\s+/).pop())
          .filter(p => p && !isNaN(Number(p)))
      ) as Set<string>;
      
      for (const pid of pids) {
        try {
          if (process.platform === 'win32') {
            execSync(`taskkill /F /PID ${pid}`, { stdio: 'ignore' });
          } else {
            process.kill(Number(pid), 'SIGKILL');
          }
        } catch (_) {}
      }
    } catch (_) {}
  }
}

/**
 * Start tunnel with cascading fallback: localhostrun → pinggy → ngrok.
 * After getting a URL from any provider, probes /health:
 *   PASS → announce URL, stay alive until disconnect, then cycle
 *   FAIL → write 10-minute cooldown file, kill proc, try next provider
 * Cooldowns persist across restarts so a down provider stays skipped.
 */
function startTunnelWithFallback(
  host: string,
  port: number,
  token: string,
  onUrl: (url: string) => void,
  options?: any
) {
  const preferred = options?.tunnel;
  const PROVIDERS = ['localhostrun', 'pinggy', 'ngrok'];
  if (preferred && PROVIDERS.includes(preferred)) {
    const idx = PROVIDERS.indexOf(preferred);
    PROVIDERS.splice(idx, 1);
    PROVIDERS.unshift(preferred);
  }

  const ATTEMPT_TIMEOUT_MS = 25000;
  const RETRY_DELAY_MS    = 2000;
  const NGROK_API         = 'http://127.0.0.1:4040';

  let activeProc: ChildProcess | null = null;
  let stopped = false;
  let providerIndex = 0;

  /** Attempt one provider, return the public base URL or null on failure. */
  const tryProvider = async (provider: string): Promise<string | null> => {
    tunnelUrl = null;

    if (provider === 'ngrok') {
      // ngrok: URL comes from local HTTP API, not stdout parsing
      let proc: ChildProcess;
      try {
        proc = startTunnel('ngrok', host, port, options?.ngrok);
      } catch (e: any) {
        console.error(`[tunnel-fallback] ngrok spawn failed: ${e.message}`);
        return null;
      }
      activeProc = proc;
      tunnelProcess = proc;
      try {
        return await discoverNgrokUrl(NGROK_API, ATTEMPT_TIMEOUT_MS);
      } catch (e: any) {
        console.error(`[tunnel-fallback] ngrok: ${e.message}`);
        killTunnelProc(proc);
        return null;
      }
    }

    // SSH-based providers: localhostrun, pinggy
    const { proc, promise } = attemptTunnel(provider, host, port, ATTEMPT_TIMEOUT_MS);
    activeProc = proc;
    tunnelProcess = proc;
    try {
      return await promise;
    } catch (e: any) {
      console.error(`[tunnel-fallback] ${provider}: ${e.message}`);
      if (proc) killTunnelProc(proc);
      return null;
    }
  };

  const run = async () => {
    console.error(`[plan-audit-map] Waiting for local MCP server to start on ${host}:${port}...`);
    await waitForLocalSse(host, port, token);

    while (!stopped) {
      const provider = PROVIDERS[providerIndex % PROVIDERS.length];
      providerIndex++;

      if (tunnelOnCooldown(provider)) {
        await new Promise(r => setTimeout(r, 500));
        continue;
      }

      console.error(`[tunnel-fallback] Trying provider: ${provider} (attempt ${providerIndex})`);
      const publicBase = await tryProvider(provider);

      if (!publicBase) {
        if (!stopped) await new Promise(r => setTimeout(r, RETRY_DELAY_MS));
        continue;
      }

      // Got URL — probe before announcing
      console.error(`[tunnel-fallback] Probing ${provider} URL: ${publicBase}/health`);
      const healthy = await probePublicHealth(publicBase);

      if (!healthy) {
        tunnelSetCooldown(provider, 'health probe failed after URL received');
        killTunnelProc(activeProc);
        if (!stopped) await new Promise(r => setTimeout(r, RETRY_DELAY_MS));
        continue;
      }

      // Healthy — announce and hold until disconnect
      tunnelClearCooldown(provider);
      console.error(`[tunnel-fallback] SUCCESS via ${provider}: ${publicBase}`);
      onUrl(publicBase);

      await new Promise<void>(resolve => {
        const p = activeProc;
        if (!p) { resolve(); return; }
        p.on('exit',  resolve);
        p.on('close', resolve);
        p.on('error', resolve);
      });

      if (stopped) break;
      console.error(`[tunnel-fallback] ${provider} disconnected — cycling to next...`);
      if (!stopped) await new Promise(r => setTimeout(r, RETRY_DELAY_MS));
    }
  };

  const handle = { stop: () => { stopped = true; killTunnelProc(activeProc); } };
  setTimeout(run, 1000);
  return handle;
}

function waitForLocalSse(host: string, port: number, token: string): Promise<void> {
  return new Promise((resolve) => {
    const check = () => {
      const path = token ? `/sse?token=${encodeURIComponent(token)}` : '/sse';
      // @ts-ignore
      const req = http.request({ host, port, path, method: 'GET', timeout: 1000 }, (res) => {
        if (res.statusCode === 200 || res.statusCode === 401) {
          resolve();
        } else {
          setTimeout(check, 500);
        }
      });
      req.on('error', () => {
        setTimeout(check, 500);
      });
      req.end();
    };
    check();
  });
}



function printBanner(publicBase: string, host: string, port: number, token: string) {
  const sseUrl = `${publicBase}/sse`;
  const tokenUrl = token ? `${sseUrl}?token=${encodeURIComponent(token)}` : sseUrl;
  
  console.error('\n' + '═'.repeat(78));
  console.error('Map. Think. Do. Remote MCP is live (integrated)');
  console.error('═'.repeat(78));
  console.error(`Local SSE:       http://${host}:${port}/sse`);
  console.error(`Public base:     ${publicBase}`);
  console.error(`Public SSE URL:  ${tokenUrl}`);
  if (token) {
    console.error(`Bearer token:    ${token}`);
  }
  console.error('\nMCP Client Setup');
  console.error('  App name:       Map. Think. Do. MCP Server');
  console.error('  Description:    Structured reasoning and reflection MCP server');
  console.error(`  MCP URL:        ${tokenUrl}`);
  console.error('  Authentication: No Auth / None');
  if (token) {
    console.error('\nIf your client supports Bearer auth instead, use:');
    console.error(`  URL:            ${sseUrl}`);
    console.error(`  Authorization:  Bearer ***`);
  }
  console.error('\nKeep this terminal open. Press Ctrl+C to stop server and tunnel.');
  console.error('\n  Test tunnel:    ' + publicBase + '/health  (open in browser)');
  console.error('═'.repeat(78) + '\n');
  
  // Self-probe: verify traffic actually flows through the tunnel
  // Uses Node's built-in https module to fetch the public /health URL
  // and logs a clear PASS/FAIL so the user can distinguish:
  //   PASS = tunnel works, issue is Grok-side or firewall on Grok's end
  //   FAIL = tunnel is broken or firewall is blocking outbound/return traffic
  setTimeout(() => {
    const probeUrl = `${publicBase}/health`;
    console.error('[tunnel-probe] Testing public reachability: ' + probeUrl);
    const req2 = https.get(probeUrl, { timeout: 8000 }, (res2: any) => {
      let body = '';
      res2.on('data', (c: any) => body += c);
      res2.on('end', () => {
        if (res2.statusCode === 200) {
          console.error('[tunnel-probe]  PASS — public URL is reachable from the internet.');
          console.error('[tunnel-probe]    If Grok still fails, the issue is Grok-side or its firewall.');
          console.error('[tunnel-probe]    Also open in browser to confirm: ' + probeUrl);
        } else {
          console.error(`[tunnel-probe]   Got HTTP ${res2.statusCode} — unexpected response. Check tunnel.`);
        }
      });
    });
    req2.on('error', (err: any) => {
      console.error('[tunnel-probe]  FAIL — public URL unreachable: ' + err.message);
      console.error('[tunnel-probe]    Likely cause: firewall (SimpleWall/Windows) blocking ssh.exe or node.exe.');
      console.error('[tunnel-probe]    Check SimpleWall rules for ssh.exe and node.exe.');
    });
    req2.on('timeout', () => {
      req2.destroy();
      console.error('[tunnel-probe]  FAIL — connection timed out reaching public URL.');
      console.error('[tunnel-probe]    Likely cause: firewall blocking return traffic through SSH tunnel.');
    });
  }, 3000);
}

// ── Rate Limiter ─────────────────────────────────────────────────────────────
class RateLimiter {
  private hits = new Map<string, number[]>();
  private readonly windowMs: number;
  private readonly maxHits: number;

  constructor(windowMs: number, maxHits: number) {
    this.windowMs = windowMs;
    this.maxHits = maxHits;
  }

  check(key: string): boolean {
    const now = Date.now();
    const timestamps = this.hits.get(key) || [];
    // Remove old entries
    const recent = timestamps.filter(t => now - t < this.windowMs);
    this.hits.set(key, recent);
    if (recent.length >= this.maxHits) {
      return false;
    }
    recent.push(now);
    return true;
  }

  cleanup() {
    const now = Date.now();
    for (const [key, timestamps] of this.hits) {
      const recent = timestamps.filter(t => now - t < this.windowMs);
      if (recent.length === 0) {
        this.hits.delete(key);
      } else {
        this.hits.set(key, recent);
      }
    }
  }
}

// ── Constant-time string comparison ─────────────────────────────────────────
function safeEqual(a: string, b: string): boolean {
  if (a.length !== b.length) return false;
  let result = 0;
  for (let i = 0; i < a.length; i++) {
    result |= a.charCodeAt(i) ^ b.charCodeAt(i);
  }
  return result === 0;
}

// ── Get client IP ───────────────────────────────────────────────────────────
function getClientIp(req: http.IncomingMessage): string {
  const xff = req.headers['x-forwarded-for'];
  if (typeof xff === 'string') return xff.split(',')[0].trim();
  return req.socket?.remoteAddress || 'unknown';
}

export async function runServer(debugFlag = false, options?: any): Promise<void> {
  // Initialize config manager and get config
  await configManager.init();
  const config = await configManager.getConfig();

  // Apply debug flag if specified
  if (debugFlag) {
    await configManager.setValue('debug', true);
  }

  const serverMeta = { name: 'plan-audit-map', version: '1.0.0' } as const;

  // Configure server capabilities based on config
  const capabilities: Partial<ServerCapabilities> = {
    tools: {},
    resources: {},
    completions: {}, // Add completions capability
  };

  // Only add prompts capability if enabled
  if (config.promptsEnabled) {
    capabilities.prompts = {};
  }

  const srv = new Server(serverMeta, { capabilities });
  const logic = new CodeReasoningServer(config);

  // Initialize the cognitive orchestrator with dependency injection
  await logic.initialize();

  // Initialize prompt manager if enabled
  let promptManager: PromptManager | undefined;
  if (config.promptsEnabled) {
    promptManager = new PromptManager(CONFIG_DIR);
    console.error('Prompts capability enabled');
    if (CONFIG_DIR === LEGACY_CONFIG_DIR) {
      console.error(
        `Using legacy config directory ${LEGACY_CONFIG_DIR}. Create ${DEFAULT_CONFIG_DIR} to migrate to the new canonical path.`
      );
    }

    // Load custom prompts from the standard location
    console.error(`Loading custom prompts from ${CUSTOM_PROMPTS_DIR}`);
    await promptManager.loadCustomPrompts(CUSTOM_PROMPTS_DIR);

    // Add prompt handlers
    srv.setRequestHandler(ListPromptsRequestSchema, async () => {
      const prompts = promptManager?.getAllPrompts() || [];
      console.error(`Returning ${prompts.length} prompts`);
      return { prompts };
    });

    srv.setRequestHandler(GetPromptRequestSchema, async req => {
      const promptName = req.params.name;
      const args = (req.params.arguments || {}) as Record<string, string>;

      try {
        if (!promptManager) {
          throw new McpError(ErrorCode.InternalError, 'Prompt manager not initialized');
        }

        console.error('Getting prompt', {
          promptName,
          ...summarizePromptArgsForLogging(args),
        });

        // Get the prompt result
        const result = promptManager.applyPrompt(promptName, args);

        // Return the result in the format expected by MCP
        return {
          messages: result.messages,
          _meta: {},
        };
      } catch (err) {
        const e = err as Error;
        console.error('Prompt error', {
          promptName,
          ...summarizePromptArgsForLogging(args),
          error: e.message,
        });
        if (err instanceof McpError) {
          throw err;
        }
        if (isPromptClientError(e.message)) {
          throw new McpError(ErrorCode.InvalidParams, e.message);
        }
        throw new McpError(ErrorCode.InternalError, GENERIC_PROMPT_ERROR_MESSAGE);
      }
    });

    // Add handler for completion/complete requests
    srv.setRequestHandler(CompleteRequestSchema, async req => {
      try {
        if (!promptManager) {
          throw new McpError(ErrorCode.InternalError, 'Prompt manager not initialized');
        }

        // Check if this is a prompt reference
        if (req.params.ref.type !== 'ref/prompt') {
          return {
            completion: {
              values: [],
            },
          };
        }

        const promptName = req.params.ref.name;
        const argName = req.params.argument.name;

        console.error('Completing prompt argument', { promptName, argName });

        const completionValues = promptManager.getCompletionValues(promptName, argName);
        return {
          completion: {
            values: completionValues,
          },
        };
      } catch (err) {
        const e = err as Error;
        console.error('Completion error:', e.message);
        return {
          completion: {
            values: [],
          },
        };
      }
    });
  } else {
    // Keep the empty handlers if prompts disabled
    srv.setRequestHandler(ListPromptsRequestSchema, async () => ({ prompts: [] }));

    // Add empty handler for completion requests as well when prompts are disabled
    srv.setRequestHandler(CompleteRequestSchema, async () => ({
      completion: {
        values: [],
      },
    }));
  }

  // Existing handlers
  srv.setRequestHandler(ListResourcesRequestSchema, async () => ({ resources: [] }));
  srv.setRequestHandler(ListToolsRequestSchema, async () => ({
    tools: [PLAN_AUDIT_MAP_TOOL, PLAN_AUDIT_MAP_FEEDBACK_TOOL],
  }));
  srv.setRequestHandler(CallToolRequestSchema, async req => {
    if (isSupportedToolName(req.params.name)) {
      return logic.processThought(req.params.arguments);
    } else if (req.params.name === PLAN_AUDIT_MAP_FEEDBACK_TOOL_NAME) {
      return logic.processFeedback(req.params.arguments);
    } else {
      throw new McpError(ErrorCode.MethodNotFound, `Unknown tool: ${req.params.name}`);
    }
  });

  const shouldRunSse = options?.sse || options?.remote;

  if (shouldRunSse) {
    let host = options?.host || '127.0.0.1';
    const port = parseInt(options?.port || '8002', 10);
    const maxConnections = parseInt(options?.['max-connections'] || '50', 10);
    const corsOrigin = options?.['cors-origin'] || '*';
    const disableDashboard = options?.['no-dashboard'] || false;
    const quiet = options?.quiet || false;
    const tlsCert = options?.['tls-cert'];
    const tlsKey = options?.['tls-key'];
    
    cleanupPort(port);
    
    if (options?.local) {
      try {
        const interfaces = os.networkInterfaces();
        let resolved = '127.0.0.1';
        for (const name of Object.keys(interfaces)) {
          const iface = interfaces[name];
          if (iface) {
            for (const alias of iface) {
              if (alias.family === 'IPv4' && !alias.internal) {
                resolved = alias.address;
                break;
              }
            }
          }
        }
        host = resolved;
        console.error(`[plan-audit-map] Local network mode active. Resolved IP: ${host}`);
      } catch (e: any) {
        console.error(`[plan-audit-map] Could not resolve local network IP: ${e.message}. Defaulting to 127.0.0.1`);
      }
    }
    
    let token = options?.token;
    if (options?.['token-file']) {
      try {
        token = fs.readFileSync(options['token-file'], 'utf8').trim();
      } catch (e: any) {
        console.error(`[plan-audit-map] Failed to read token file: ${e.message}`);
        process.exit(1);
      }
    }

    const sseTransports = new Map<string, SSEServerTransport>();
    const rateLimiter = new RateLimiter(60000, 30); // 30 requests per minute per IP
    const connectionRateLimiter = new RateLimiter(60000, 10); // 10 connections per minute per IP
    
    // Periodic cleanup of rate limiter
    const rateCleanupInterval = setInterval(() => {
      rateLimiter.cleanup();
      connectionRateLimiter.cleanup();
    }, 60000);

    const srvHttp = (tlsCert && tlsKey)
      ? https.createServer({
          cert: fs.readFileSync(tlsCert),
          key: fs.readFileSync(tlsKey),
        })
      : http.createServer();

    srvHttp.on('request', async (req, res) => {
      const clientIp = getClientIp(req);
      
      // Rate limiting
      if (!rateLimiter.check(clientIp)) {
        res.writeHead(429, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ error: 'Too many requests' }));
        return;
      }
      
      // Security headers
      res.setHeader('X-Content-Type-Options', 'nosniff');
      res.setHeader('X-Frame-Options', 'DENY');
      res.setHeader('X-XSS-Protection', '1; mode=block');
      res.setHeader('Referrer-Policy', 'no-referrer');
      res.setHeader('Strict-Transport-Security', 'max-age=31536000; includeSubDomains');
      
      // Enable CORS
      res.setHeader('Access-Control-Allow-Origin', corsOrigin);
      res.setHeader('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
      res.setHeader('Access-Control-Allow-Headers', 'Content-Type, Authorization');
      
      if (req.method === 'OPTIONS') {
        res.writeHead(204).end();
        return;
      }
      
      const parsedUrl = new URL(req.url || '', `http://${host}:${port}`);
      const pathname = parsedUrl.pathname;
      
      const checkToken = (): boolean => {
        if (!token) return true;
        let supplied = parsedUrl.searchParams.get('token');
        const authHeader = req.headers['authorization'];
        if (authHeader && authHeader.toLowerCase().startsWith('bearer ')) {
          supplied = authHeader.substring(7).trim();
        }
        return safeEqual(supplied || '', token);
      };
      
      if (pathname === '/sse' && req.method === 'GET') {
        if (!checkToken()) {
          res.writeHead(401).end('Unauthorized');
          return;
        }
        
        // Connection rate limiting
        if (!connectionRateLimiter.check(clientIp)) {
          res.writeHead(429).end('Too many connections');
          return;
        }
        
        // Max connections check
        if (sseTransports.size >= maxConnections) {
          res.writeHead(503).end('Server at capacity');
          return;
        }
        
        const transport = new SSEServerTransport('/messages', res);
        sseTransports.set(transport.sessionId, transport);
        _last_session_id = transport.sessionId;
        
        transport.onclose = () => {
          sseTransports.delete(transport.sessionId);
          if (_last_session_id === transport.sessionId) {
            _last_session_id = null;
          }
        };
        
        await srv.connect(transport);
        return;
      }
      
      if (pathname === '/messages' && req.method === 'POST') {
        const sessionId = parsedUrl.searchParams.get('sessionId');
        if (!sessionId) {
          res.writeHead(400).end('sessionId is required');
          return;
        }
        const transport = sseTransports.get(sessionId);
        if (!transport) {
          res.writeHead(404).end('Session not found');
          return;
        }
        await transport.handlePostMessage(req, res);
        return;
      }
      
      // Grok compatibility patch
      if (pathname === '/sse' && req.method === 'POST') {
        if (!checkToken()) {
          res.writeHead(401).end('Unauthorized');
          return;
        }
        let sessionId = parsedUrl.searchParams.get('sessionId');
        if (!sessionId) {
          sessionId = _last_session_id || '';
        }
        const transport = sseTransports.get(sessionId);
        if (!transport) {
          res.writeHead(404).end('Session not found');
          return;
        }
        await transport.handlePostMessage(req, res);
        return;
      }
      
      if (pathname === '/' && req.method === 'GET') {
        if (disableDashboard) {
          res.writeHead(404).end('Not found');
          return;
        }
        res.writeHead(200, { 'Content-Type': 'text/html' });
        res.end(DASHBOARD_HTML);
        return;
      }
      
      if (pathname === '/api/thoughts' && req.method === 'GET') {
        if (disableDashboard) {
          res.writeHead(404).end('Not found');
          return;
        }
        try {
          const thoughts = await logic.memoryStore.queryThoughts({ limit: 50 });
          res.writeHead(200, { 'Content-Type': 'application/json' });
          res.end(JSON.stringify({ thoughts }));
        } catch (err: any) {
          res.writeHead(500, { 'Content-Type': 'application/json' });
          res.end(JSON.stringify({ error: err.message }));
        }
        return;
      }
      
      if (pathname === '/health' && req.method === 'GET') {
        res.writeHead(200, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({
          status: 'ok',
          server: 'plan-audit-map',
          timestamp: new Date().toISOString()
        }));
        return;
      }
      
      res.writeHead(404).end('Not found');
    });

    // Request timeout
    srvHttp.setTimeout(30000);
    
    srvHttp.listen(port, host, () => {
      console.error(`[plan-audit-map] Server listening at http://${host}:${port}`);
    });

    if (options?.remote) {
      try {
        startTunnelWithFallback(
          host,
          port,
          token,
          (publicBase) => {
            if (!quiet) {
              printBanner(publicBase, host, port, token);
            } else {
              console.error(`[plan-audit-map] Remote URL: ${publicBase}/sse`);
            }
          },
          options
        );
      } catch (err: any) {
        console.error(`FATAL: Failed to start tunnel: ${err.message}`);
        process.exit(1);
      }
    }

    const shutdown = async (sig: string) => {
      console.error(`↩ shutdown on ${sig}`);
      clearInterval(rateCleanupInterval);
      try {
        if (tunnelProcess) {
          console.error(`[plan-audit-map] stopping tunnel process...`);
          if (process.platform === 'win32') {
            spawn('taskkill', ['/F', '/T', '/PID', tunnelProcess.pid!.toString()]);
          } else {
            tunnelProcess.kill();
          }
        }
      } catch (err) {}
      
      try {
        await logic.getCognitiveOrchestrator().dispose();
        await logic.destroy();
      } catch (err) {}
      
      try {
        await srv.close();
      } catch (err) {}
      
      process.exit(0);
    };

    ['SIGINT', 'SIGTERM'].forEach(s => process.on(s, () => shutdown(s)));
    process.on('uncaughtException', (err: Error) => {
      console.error(' uncaught', err);
      shutdown('uncaughtException');
    });
    process.on('unhandledRejection', (r: unknown) => {
      console.error(' unhandledRejection', r);
      shutdown('unhandledRejection');
    });
    return;
  }

  const transport = new FilteredStdioServerTransport();

  // Monitor transport health
  const healthCheckInterval = setInterval(() => {
    if (!transport.isReady()) {
      const error = transport.getError();
      console.error(' Transport health check failed:', error?.message || 'Unknown error');
      shutdown('transport_failure');
    }
  }, 5000); // Check every 5 seconds

  // Idempotent shutdown — safe to call from any exit path.
  let shuttingDown = false;
  const shutdown = async (sig: string) => {
    if (shuttingDown) return;
    shuttingDown = true;

    // Always clear the health-check interval first so it cannot re-enter shutdown.
    clearInterval(healthCheckInterval);

    console.error(`↩ shutdown on ${sig}`);

    // Cleanup cognitive components
    try {
      console.error(' Cleaning up cognitive systems...');
      await logic.getCognitiveOrchestrator().dispose();
      await logic.destroy();
      console.error(' Cognitive systems cleaned up');
    } catch (err) {
      console.error(' Error cleaning up cognitive systems:', err);
    }

    // Cleanup transport (avoid double-close)
    try {
      await srv.close();
      console.error(' Server closed');
    } catch (err) {
      console.error(' Error closing server:', err);
    }

    try {
      await transport.close();
      console.error(' Transport closed');
    } catch (err) {
      console.error(' Error closing transport:', err);
    }

    process.exit(0);
  };

  await srv.connect(transport);

  console.error(' Map. Think. Do. - Server ready');
  console.error(' MAP: Problem decomposition active');
  console.error(' THINK: 8 cognitive perspectives available');
  console.error(' DO: Structured reasoning enabled');
  console.error(' Memory: SQLite persistence active');
  console.error(' Bias Detection: Online');
  console.error(` Tool: ${PLAN_AUDIT_MAP_TOOL_NAME}`);
  console.error(`↩ Legacy tool alias accepted: ${LEGACY_TOOL_NAME}`);
  if (config.promptsEnabled) {
    console.error(' Prompts: Enabled');
  }
  console.error(' Map the problem. Think it through. Do what matters.');

  ['SIGINT', 'SIGTERM'].forEach(s => process.on(s, () => shutdown(s)));
  process.on('uncaughtException', (err: Error) => {
    console.error(' uncaught', err);
    shutdown('uncaughtException');
  });
  process.on('unhandledRejection', (r: unknown) => {
    console.error(' unhandledRejection', r);
    shutdown('unhandledRejection');
  });
}

// Self-execute when run directly ------------------------------------------------
if (import.meta.url === `file://${process.argv[1]}`) {
  runServer(process.argv.includes('--debug')).catch(err => {
    console.error('FATAL: failed to start', err);
    process.exit(1);
  });
}

// NOTE: InMemoryStore has been replaced by SQLiteStore for REAL persistence
// See /src/memory/sqlite-store.ts for implementation
