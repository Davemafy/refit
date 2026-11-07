// Use this opt-in adapter when a provider cannot combine tool turns with its
// strict schema decoder. Keep the caller's own final-output schema validator.
export function promptSchemaDuringToolCalls(body) {
  const schema = body.response_format?.type === "json_schema"
    ? body.response_format.json_schema?.schema : undefined;
  if (!Array.isArray(body.tools) || !body.tools.length ||
      !Array.isArray(body.messages) || !schema) return body;
  const { response_format, ...request } = body;
  return {
    ...request,
    messages: [...request.messages, {
      role: "system",
      content: "Tool calls are available before the final response. For the final response only, emit raw JSON matching this schema. Do not use Markdown, code fences, or surrounding text. " + JSON.stringify(schema),
    }],
  };
}
