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
		for key := range v {
			keys = append(keys, key)
		}
		sort.Strings(keys)
		var out bytes.Buffer
		out.WriteByte('{')
		for i, key := range keys {
			if i > 0 {
				out.WriteByte(',')
			}
			keyBytes, _ := json.Marshal(key)
			child, err := canonical(v[key])
			if err != nil {
				return nil, err
			}
			out.Write(keyBytes)
			out.WriteByte(':')
			out.Write(child)
		}
		out.WriteByte('}')
		return out.Bytes(), nil
	case []any:
		var out bytes.Buffer
		out.WriteByte('[')
		for i, childValue := range v {
			if i > 0 {
				out.WriteByte(',')
			}
			child, err := canonical(childValue)
			if err != nil {
				return nil, err
			}
			out.Write(child)
		}
		out.WriteByte(']')
		return out.Bytes(), nil
	default:
		return json.Marshal(value)
	}
}

func requireString(payload map[string]any, field string) string {
	value, ok := payload[field].(string)
	if !ok || value == "" {
		panic("invalid runner " + field)
	}
	return value
}

func validateEnvelope(payload map[string]any) {
	required := map[string]bool{"protocol": true, "message_type": true, "request_id": true, "payload": true}
	allowed := map[string]bool{
		"protocol": true, "message_type": true, "request_id": true, "payload": true,
		"execution_id": true, "attempt_id": true, "capabilities": true,
	}
	for key := range payload {
		if !allowed[key] {
			panic("runner envelope contains unknown fields")
		}
		delete(required, key)
	}
	if len(required) != 0 {
		panic("runner envelope is missing required fields")
	}
	if requireString(payload, "protocol") != "ronin/runner/v1" {
		panic("unsupported runner protocol")
	}
	messageType := requireString(payload, "message_type")
	if !allowedTypes[messageType] {
		panic("invalid runner message type")
	}
	requestID := requireString(payload, "request_id")
	if len(requestID) > 256 {
		panic("invalid runner request id")
	}
	if _, ok := payload["payload"].(map[string]any); !ok {
		panic("invalid runner payload")
	}
	for _, field := range []string{"execution_id", "attempt_id"} {
		if value, ok := payload[field]; ok {
			if text, valid := value.(string); !valid || text == "" {
				panic("invalid runner " + field)
			}
		}
	}
	if value, ok := payload["capabilities"]; ok {
		capabilities, valid := value.([]any)
		if !valid {
			panic("invalid runner capabilities")
		}
		previous := ""
		for index, item := range capabilities {
			capability, valid := item.(string)
			if !valid || capability == "" || (index > 0 && capability <= previous) {
				panic("invalid runner capabilities ordering")
			}
			previous = capability
		}
	}
}

func main() {
	path := "tests/golden/runner_protocol_v1.json"
	if len(os.Args) == 2 {
		path = os.Args[1]
	}
	raw, err := os.ReadFile(path)
	if err != nil {
		panic(err)
	}
	var document struct {
		Schema   string `json:"schema"`
		Fixtures []struct {
			Name      string         `json:"name"`
			Payload   map[string]any `json:"payload"`
			Canonical string         `json:"canonical"`
		} `json:"fixtures"`
	}
	if err := json.Unmarshal(raw, &document); err != nil {
		panic(err)
	}
	if document.Schema != "ronin.runner.protocol/v1" || len(document.Fixtures) == 0 {
		panic("invalid runner fixture document")
	}
	for _, fixture := range document.Fixtures {
		validateEnvelope(fixture.Payload)
		canonicalBytes, err := canonical(fixture.Payload)
		if err != nil {
			panic(err)
		}
		if string(canonicalBytes) != fixture.Canonical {
			panic(fmt.Sprintf("fixture %s canonical bytes mismatch", fixture.Name))
		}
	}
	fmt.Printf("runner protocol fixtures: ok (%d)\n", len(document.Fixtures))
}
