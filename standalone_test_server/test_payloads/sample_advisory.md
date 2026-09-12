# Threat Report: Operation Red Falcon

**Date**: October 12, 2026

An internal review has detected unauthorized lateral movement originating from host `internal-dev.corp.acme.net` leading to access via `10.4.52.1`. The threat actors appear to have obtained a leaked database password (which was unfortunately committed to git as `password="Sup3rS3cr3t!"`).

They exploited CVE-2026-9999 to gain access. Rapid remediation includes rotating the API key immediately. 
