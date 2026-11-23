{{- define "operator-library.resources" -}}
apiVersion: v1
kind: Namespace
metadata:
  name: fixture-operator
---
apiVersion: operators.coreos.com/v1
kind: OperatorGroup
metadata:
  name: fixture
  namespace: fixture-operator
---
apiVersion: operators.coreos.com/v1alpha1
kind: Subscription
metadata:
  name: fixture
  namespace: fixture-operator
{{- end }}
