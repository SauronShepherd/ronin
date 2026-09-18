// Command runner_protocol_check independently checks ronin/runner/v1 fixtures.
package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"os"
	"sort"
)

var allowedTypes = map[string]bool{
	"capabilities": true, "dispatch": true, "heartbeat": true,
	"cancel": true, "result": true, "error": true,
}

func canonical(value any) ([]byte, error) {
	switch v := value.(type) {
	case map[string]any:
		keys := make([]string, 0, len(v))
		for key := range v { keys = append(keys, key) }
		sort.Strings(keys)
		var out bytes.Buffer
		out.WriteByte('{')
		for i, key := range keys {
			if i > 0 { out.WriteByte(',') }
			keyBytes, _ := json.Marshal(key)
			child, err := canonical(v[key]); if err != nil { return nil, err }
			out.Write(keyBytes); out.WriteByte(':'); out.Write(child)
		}
		out.WriteByte('}')
		return out.Bytes(), nil
	case []any:
		var out bytes.Buffer; out.WriteByte('[')
		for i, childValue := range v {
			if i > 0 { out.WriteByte(',') }
			child, err := canonical(childValue); if err != nil { return nil, err }
			out.Write(child)
		}
		out.WriteByte(']'); return out.Bytes(), nil
	default:
		return json.Marshal(value)
	}
}

func main() {
	path := "tests/golden/runner_protocol_v1.json"
	if len(os.Args) == 2 { path = os.Args[1] }
	raw, err := os.ReadFile(path); if err != nil { panic(err) }
	var document struct { Schema string `json:"schema"`; Fixtures []struct {
		Name string `json:"name"`; Payload map[string]any `json:"payload"`; Canonical string `json:"canonical"`
	} `json:"fixtures"` }
	if err := json.Unmarshal(raw, &document); err != nil { panic(err) }
	if document.Schema != "ronin.runner.protocol/v1" || len(document.Fixtures) == 0 { panic("invalid runner fixture document") }
	for _, fixture := range document.Fixtures {
		if fixture.Payload["protocol"] != "ronin/runner/v1" { panic("unsupported runner protocol") }
		messageType, ok := fixture.Payload["message_type"].(string); if !ok || !allowedTypes[messageType] { panic("invalid runner message type") }
		if _, ok := fixture.Payload["request_id"].(string); !ok { panic("invalid runner request id") }
		if _, ok := fixture.Payload["payload"].(map[string]any); !ok { panic("invalid runner payload") }
		canonicalBytes, err := canonical(fixture.Payload); if err != nil { panic(err) }
		if string(canonicalBytes) != fixture.Canonical { panic(fmt.Sprintf("fixture %s canonical bytes mismatch", fixture.Name)) }
	}
	fmt.Printf("runner protocol fixtures: ok (%d)\n", len(document.Fixtures))
}
