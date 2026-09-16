{{- define "ronin.name" -}}
{{- .Chart.Name -}}
{{- end -}}
{{- define "ronin.fullname" -}}
{{- include "ronin.name" . -}}
{{- end -}}
