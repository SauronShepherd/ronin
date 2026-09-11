package main

import (
	"bytes"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"math"
	"os"
	"sort"
	"strconv"
	"strings"
)

type vector struct {
	Name      string `json:"name"`
	Source    string `json:"source_json"`
	Canonical string `json:"canonical_utf8"`
	SHA       string `json:"sha256"`
}
type rejection struct {
	Name   string `json:"name"`
	Source string `json:"source_json"`
}
type fixture struct {
	Schema     string      `json:"schema"`
	Vectors    []vector    `json:"vectors"`
	Rejections []rejection `json:"rejections"`
}

func parseValue(dec *json.Decoder) (any, error) {
	token, err := dec.Token()
	if err != nil {
		return nil, err
	}
	switch value := token.(type) {
	case json.Delim:
		switch value {
		case '{':
			object := map[string]any{}
			for dec.More() {
				keyToken, err := dec.Token()
				if err != nil {
					return nil, err
				}
				key, ok := keyToken.(string)
				if !ok {
					return nil, fmt.Errorf("object key is not a string")
				}
				if _, exists := object[key]; exists {
					return nil, fmt.Errorf("duplicate object member %q", key)
				}
				child, err := parseValue(dec)
				if err != nil {
					return nil, err
				}
				object[key] = child
			}
			end, err := dec.Token()
			if err != nil || end != json.Delim('}') {
				return nil, fmt.Errorf("invalid object")
			}
			return object, nil
		case '[':
			array := []any{}
			for dec.More() {
				child, err := parseValue(dec)
				if err != nil {
					return nil, err
				}
				array = append(array, child)
			}
			end, err := dec.Token()
			if err != nil || end != json.Delim(']') {
				return nil, fmt.Errorf("invalid array")
			}
			return array, nil
		}
	}
	if number, ok := token.(json.Number); ok && strings.ContainsAny(number.String(), ".eE") {
		parsed, err := strconv.ParseFloat(number.String(), 64)
		if err != nil || math.IsInf(parsed, 0) || math.IsNaN(parsed) {
			return nil, fmt.Errorf("non-finite number")
		}
	}
	return token, nil
}

func parse(source string) (any, error) {
	dec := json.NewDecoder(bytes.NewBufferString(source))
	dec.UseNumber()
	value, err := parseValue(dec)
	if err != nil {
		return nil, err
	}
	if _, err = dec.Token(); err != io.EOF {
		if err == nil {
			return nil, fmt.Errorf("trailing JSON value")
		}
		return nil, err
	}
	return value, nil
}

func canonical(value any) ([]byte, error) {
	var out bytes.Buffer
	enc := json.NewEncoder(&out)
	enc.SetEscapeHTML(false)
	enc.SetIndent("", "")
	if err := enc.Encode(value); err != nil {
		return nil, err
	}
	return bytes.TrimSuffix(out.Bytes(), []byte("\n")), nil
}

func main() {
	path := "tests/golden/canonical_json_v1.json"
	if len(os.Args) == 2 {
		path = os.Args[1]
	} else if len(os.Args) > 2 {
		fmt.Fprintln(os.Stderr, "usage: canonical_json_check [golden-file]")
		os.Exit(2)
	}
	raw, err := os.ReadFile(path)
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
	var f fixture
	if err := json.Unmarshal(raw, &f); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
	if f.Schema != "ronin.canonical-json-goldens/v1" {
		fmt.Fprintln(os.Stderr, "unexpected golden schema")
		os.Exit(1)
	}
	names := make([]string, 0, len(f.Vectors))
	for _, v := range f.Vectors {
		value, err := parse(v.Source)
		if err != nil {
			fmt.Fprintf(os.Stderr, "%s: parse: %v\n", v.Name, err)
			os.Exit(1)
		}
		actual, err := canonical(value)
		if err != nil {
			fmt.Fprintf(os.Stderr, "%s: encode: %v\n", v.Name, err)
			os.Exit(1)
		}
		if string(actual) != v.Canonical {
			fmt.Fprintf(os.Stderr, "%s: canonical bytes mismatch\n", v.Name)
			os.Exit(1)
		}
		digest := sha256.Sum256(actual)
		if hex.EncodeToString(digest[:]) != v.SHA {
			fmt.Fprintf(os.Stderr, "%s: digest mismatch\n", v.Name)
			os.Exit(1)
		}
		names = append(names, v.Name)
	}
	for _, r := range f.Rejections {
		if _, err := parse(r.Source); err == nil {
			fmt.Fprintf(os.Stderr, "%s: invalid input was accepted\n", r.Name)
			os.Exit(1)
		}
	}
	sort.Strings(names)
	fmt.Printf("canonical JSON goldens: PASS (%d vectors, %d rejections)\n", len(f.Vectors), len(f.Rejections))
}
