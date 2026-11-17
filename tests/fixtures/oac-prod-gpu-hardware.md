<!-- A100/H100 table excerpt from CCI-MOC/oac-infra at fe48c77:
docs/hardware-and-network-configuration.md. Rows preserved verbatim. -->

### A100s

|    Node Name    | Resource Class | IPMI Address |      Networking       | Purpose                  |
| ----------------| -------------- | ------------ | --------------------- | ------------------------ |
| MOC-R8PAC23U26  | a100           | 10.2.18.126  | NIC1: 216, NIC2: 2313 | Prod Workload Compute    |
| MOC-R8PAC23U31  | a100           | 10.2.18.131  | NIC1: 216, NIC2: 2313 | Prod Workload Compute    |

### H100s

|    Node Name    | Resource Class | IPMI Address |      Networking       | Purpose                  |
| ----------------| -------------- | ------------ | --------------------- | ------------------------ |
| MOC-R4PCC02U30  | h100           | 10.2.19.130  | NIC1: 216, NIC2: 2313 | Prod Workload Compute    |
| MOC-R4PCC02U32  | h100           | 10.2.19.132  | NIC1: 225             | OAC Bare Metal           |
| MOC-R4PCC04U03  | h100           | 10.2.20.103  | NIC1: 225             | OAC Bare Metal           |
| MOC-R4PCC04U09  | h100           | 10.2.20.109  | NIC1: 216, NIC2: 2313 | Prod Workload Compute    |
| MOC-R4PCC04U11  | h100           | 10.2.20.111  | NIC1: 216, NIC2: 2313 | Prod Workload Compute    |
| MOC-R4PCC04U12  | h100           | 10.2.20.112  | NIC1: 216, NIC2: 2313 | Prod Workload Compute    |
| MOC-R4PCC04U16  | h100           | 10.2.20.116  | NIC1: 216, NIC2: 2313 | Prod Workload Compute    |
