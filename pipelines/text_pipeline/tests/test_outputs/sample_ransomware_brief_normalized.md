# CISA Urgent Advisory: Ransomware Indicators

Advisory Date: 2026-07-19. Priority: CRITICAL.

Threat Actor: LockBit 3.0 observed targeting VMware ESXi infrastructure.

Attacker leveraged CVE-2024-37085 for authentication bypass.


| IOC Type | Indicator Value                                                  | Context          |
| -------- | ---------------------------------------------------------------- | ---------------- |
| IPv4     | 203.0.113.50                                                     | C2 Drop point    |
| SHA256   | ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad | Encrypter binary |