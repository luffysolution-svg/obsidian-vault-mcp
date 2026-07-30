import { execFile } from "node:child_process";

import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { Type } from "typebox";


const CLI_COMMAND = "obsidian-vault-mcp";
const CLI_TIMEOUT_MS = 660_000;
const MAX_OUTPUT_BYTES = 1024 * 1024;

const toolParameters = Type.Record(Type.String(), Type.Unknown(), {
  description: "Arguments forwarded unchanged to the corresponding Obsidian Vault MCP JSON CLI tool.",
});

const tools = [
  ["literature_doctor", "Check configuration and local integration readiness."],
  ["literature_config_get", "Read the effective V3 vault configuration."],
  ["literature_config_validate", "Validate a V3 vault configuration."],
  ["literature_config_initialize", "Initialize the single V3 vault configuration file."],
  ["zotero_ping", "Check connectivity to the local Zotero API."],
  ["zotero_search_items", "Search Zotero items with complete pagination."],
  ["zotero_list_collections", "List Zotero collections with complete pagination."],
  ["zotero_get_item", "Get a Zotero item by key."],
  ["zotero_get_children", "Get all child items for a Zotero item."],
  ["zotero_get_bibtex", "Get BibTeX for a Zotero item."],
  ["literature_import_item", "Import one Zotero item into the vault."],
  ["literature_import_collection", "Import every item in a Zotero collection."],
  ["literature_sync_item", "Synchronize an existing literature item."],
  ["literature_sync_collection", "Synchronize a Zotero collection."],
  ["literature_parse_mineru", "Parse one literature PDF with MinerU."],
  ["literature_parse_mineru_batch", "Parse a bounded batch of literature PDFs with MinerU."],
  ["literature_remove_mineru_output", "Remove generated MinerU output safely."],
  ["literature_rebuild_index", "Rebuild the literature index."],
  ["literature_rebuild_base", "Rebuild the Obsidian literature base."],
  ["literature_verify", "Verify literature assets, state, and links."],
  ["literature_paper_read", "Read bounded source text from one paper."],
  ["literature_retrieve", "Retrieve bounded source passages across an explicit paper scope."],
  ["literature_analysis_get", "Read one structured Analysis note."],
  ["literature_analysis_write", "Write a structured Analysis note transactionally."],
  ["literature_rebuild_analysis_base", "Rebuild the deterministic Analysis base."],
  ["literature_wiki_context", "Collect source context for a literature wiki topic."],
  ["literature_wiki_write", "Write a literature wiki topic with source keys."],
  ["literature_wiki_list", "List literature wiki topics."],
  ["literature_migrate_v1_to_v2", "Preview or apply a V1 to V2 migration."],
  ["literature_preview_transaction", "Preview a stored transaction."],
  ["literature_rollback_transaction", "Roll back a stored transaction."],
] as const;

type JsonObject = Record<string, unknown>;

interface CliInvocation {
  error: NodeJS.ErrnoException | null;
  stdout: string;
  stderr: string;
}

function boundedText(value: string): string {
  if (Buffer.byteLength(value, "utf8") <= MAX_OUTPUT_BYTES) {
    return value;
  }
  return `${Buffer.from(value, "utf8").subarray(0, MAX_OUTPUT_BYTES).toString("utf8")}\n[output truncated]`;
}

function invokeCli(toolName: string, parameters: JsonObject, cwd: string, signal: AbortSignal | undefined): Promise<CliInvocation> {
  return new Promise((resolve) => {
    let jsonArguments: string;
    try {
      jsonArguments = JSON.stringify(parameters);
    } catch (error) {
      resolve({
        error: error instanceof Error ? error : new Error(String(error)),
        stdout: "",
        stderr: "Tool arguments are not JSON serializable.",
      });
      return;
    }

    try {
      execFile(
        CLI_COMMAND,
        ["call", toolName, "--json", jsonArguments],
        {
          cwd,
          encoding: "utf8",
          maxBuffer: MAX_OUTPUT_BYTES,
          shell: false,
          signal,
          timeout: CLI_TIMEOUT_MS,
          windowsHide: true,
        },
        (error, stdout, stderr) => {
          resolve({
            error: error as NodeJS.ErrnoException | null,
            stdout: boundedText(stdout),
            stderr: boundedText(stderr),
          });
        },
      );
    } catch (error) {
      resolve({
        error: error instanceof Error ? error : new Error(String(error)),
        stdout: "",
        stderr: "",
      });
    }
  });
}

function isJsonObject(value: unknown): value is JsonObject {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function formatCliResult(toolName: string, invocation: CliInvocation) {
  const stdout = invocation.stdout.trim();
  const stderr = invocation.stderr.trim();
  let response: unknown;

  if (stdout) {
    try {
      response = JSON.parse(stdout);
    } catch (error) {
      const reason = error instanceof Error ? error.message : String(error);
      return {
        content: [
          {
            type: "text" as const,
            text: `The ${toolName} CLI returned invalid JSON: ${reason}${stderr ? `\nstderr: ${stderr}` : ""}`,
          },
        ],
        details: { stderr, stdout },
        isError: true,
      };
    }
  }

  const reportedError = isJsonObject(response) && (response.ok === false || (response.error !== undefined && response.error !== null));
  const failed = invocation.error !== null || !stdout || reportedError;
  if (failed) {
    const processMessage = invocation.error?.message ?? "CLI returned no JSON output.";
    const responseText = response === undefined ? processMessage : JSON.stringify(response, null, 2);
    return {
      content: [
        {
          type: "text" as const,
          text: boundedText(`${responseText}${stderr ? `\nstderr: ${stderr}` : ""}`),
        },
      ],
      details: {
        code: invocation.error?.code,
        response,
        stderr,
      },
      isError: true,
    };
  }

  return {
    content: [{ type: "text" as const, text: boundedText(JSON.stringify(response, null, 2)) }],
    details: { response },
  };
}

export default function obsidianVaultMcpExtension(pi: ExtensionAPI) {
  for (const [name, description] of tools) {
    pi.registerTool({
      name,
      label: name,
      description,
      parameters: toolParameters,
      async execute(_toolCallId, parameters, signal, _onUpdate, context) {
        const invocation = await invokeCli(name, parameters, context.cwd, signal);
        return formatCliResult(name, invocation);
      },
    });
  }
}
