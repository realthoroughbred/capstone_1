# ISMS-P 기술 통제 증적

Technical evidence mapping only; not an ISMS-P certification determination.

공식 기준: https://isms.kisa.or.kr/board/file/bbs_0000000000000005/316/FILE_000000000000559/2020052814323363328.pdf

## IAC-001 — 인프라 보안 형상 검사

결과: **PASS** · 검증 범위: **static**

통제: 2.10.2 클라우드 보안, 2.11.2 취약점 점검 및 조치

```json
{
  "policy_id": "IAC-001",
  "target": "Terraform validate",
  "tool": "Terraform validate",
  "scope": "static",
  "result": "PASS",
  "details": "Provider 스키마 검증. 실제 AWS plan/apply와 구분.",
  "evidence": [
    {
      "path": "evidence/terraform/validate.json",
      "sha256": "4cd9eddc4d07c5aff74dadb6b3544f98186f6705ac60e0d94d545fc42b45b9b6"
    },
    {
      "path": "evidence/terraform/fmt.txt",
      "sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    }
  ],
  "policy_name": "인프라 보안 형상 검사",
  "isms_p": [
    {
      "id": "2.10.2",
      "name": "클라우드 보안"
    },
    {
      "id": "2.11.2",
      "name": "취약점 점검 및 조치"
    }
  ],
  "violations": [],
  "remediation_executed": false,
  "remediation_method": null,
  "before": null,
  "after": null,
  "revalidation": "NOT_TESTED",
  "duration_seconds": null
}
```

## IAC-001 — 인프라 보안 형상 검사

결과: **PASS** · 검증 범위: **simulated**

통제: 2.10.2 클라우드 보안, 2.11.2 취약점 점검 및 조치

```json
{
  "policy_id": "IAC-001",
  "target": "Terraform 안전 조건",
  "tool": "Terraform 안전 조건",
  "scope": "simulated",
  "result": "PASS",
  "details": "mock provider: 기본 dry run, 공개 CIDR 금지, OIDC subject, 서명 전용 태그 예외.",
  "evidence": [
    {
      "path": "evidence/terraform/mock-tests.txt",
      "sha256": "b41793d12ce8027da67044db04e9d56fa953c8df18a457bd8850b882ed6e642b"
    }
  ],
  "policy_name": "인프라 보안 형상 검사",
  "isms_p": [
    {
      "id": "2.10.2",
      "name": "클라우드 보안"
    },
    {
      "id": "2.11.2",
      "name": "취약점 점검 및 조치"
    }
  ],
  "violations": [],
  "remediation_executed": false,
  "remediation_method": null,
  "before": null,
  "after": null,
  "revalidation": "NOT_TESTED",
  "duration_seconds": null
}
```

## IAC-001 — 인프라 보안 형상 검사

결과: **PASS** · 검증 범위: **static**

통제: 2.10.2 클라우드 보안, 2.11.2 취약점 점검 및 조치

```json
{
  "policy_id": "IAC-001",
  "target": "Checkov",
  "tool": "Checkov",
  "scope": "static",
  "result": "PASS",
  "details": "passed=111, failed=0, skipped=23; 예외는 docs/infra-notes.md.",
  "evidence": [
    {
      "path": "evidence/terraform/checkov.json",
      "sha256": "ea6778eca36073d3ae58c7a121617fb58cf1d9d19e021017775ce8e59363b625"
    }
  ],
  "policy_name": "인프라 보안 형상 검사",
  "isms_p": [
    {
      "id": "2.10.2",
      "name": "클라우드 보안"
    },
    {
      "id": "2.11.2",
      "name": "취약점 점검 및 조치"
    }
  ],
  "violations": [],
  "remediation_executed": false,
  "remediation_method": null,
  "before": null,
  "after": null,
  "revalidation": "NOT_TESTED",
  "duration_seconds": null
}
```

## NET-001 — 공개 SSH 접근 금지

결과: **PASS** · 검증 범위: **simulated**

통제: 2.6.1 네트워크 접근, 2.10.2 클라우드 보안, 2.9.4 로그 및 접속기록 관리

```json
{
  "policy_id": "NET-001",
  "target": "자동복구 단위·통합 테스트",
  "tool": "자동복구 단위·통합 테스트",
  "scope": "simulated",
  "result": "PASS",
  "details": "70개 fake-client/로컬 테스트. 실제 Config/Inspector 이벤트 아님.",
  "evidence": [
    {
      "path": "evidence/local/unit-tests.txt",
      "sha256": "7d3f82b3bca408ae975db798d7ba95cf1e06ed52fd09856819333faf8fdd6578"
    }
  ],
  "policy_name": "공개 SSH 접근 금지",
  "isms_p": [
    {
      "id": "2.6.1",
      "name": "네트워크 접근"
    },
    {
      "id": "2.10.2",
      "name": "클라우드 보안"
    },
    {
      "id": "2.9.4",
      "name": "로그 및 접속기록 관리"
    }
  ],
  "violations": [],
  "remediation_executed": false,
  "remediation_method": null,
  "before": null,
  "after": null,
  "revalidation": "NOT_TESTED",
  "duration_seconds": null
}
```

## OPS-001 — 로그 및 변경 증적 보존

결과: **PASS** · 검증 범위: **local**

통제: 2.9.1 변경관리, 2.9.4 로그 및 접속기록 관리

```json
{
  "policy_id": "OPS-001",
  "target": "Docker HTTP",
  "tool": "Docker HTTP",
  "scope": "local",
  "result": "PASS",
  "details": "비 root·읽기전용 rootfs·cap drop 환경에서 TCP8080 응답.",
  "evidence": [
    {
      "path": "evidence/image/http-response.txt",
      "sha256": "ae6ff88df0ac0c21253ed58e43b68e4e3b6ae03c89a640f7c61a317d8452a530"
    },
    {
      "path": "evidence/image/image-inspect.json",
      "sha256": "19d859b64f161c46be6be47031704374de0b52215b189a2bb98254f5c4a25ad5"
    }
  ],
  "policy_name": "로그 및 변경 증적 보존",
  "isms_p": [
    {
      "id": "2.9.1",
      "name": "변경관리"
    },
    {
      "id": "2.9.4",
      "name": "로그 및 접속기록 관리"
    }
  ],
  "violations": [],
  "remediation_executed": false,
  "remediation_method": null,
  "before": null,
  "after": null,
  "revalidation": "NOT_TESTED",
  "duration_seconds": null
}
```

## IMG-001 — HIGH/CRITICAL 이미지 취약점 관리

결과: **PASS** · 검증 범위: **local**

통제: 2.10.8 패치관리, 2.11.2 취약점 점검 및 조치

```json
{
  "policy_id": "IMG-001",
  "target": "Trivy 정상 이미지",
  "tool": "Trivy 정상 이미지",
  "scope": "local",
  "result": "PASS",
  "details": "실제 탐지 패키지 17개, HIGH/CRITICAL 0개. 미탐지 목록은 통과시키지 않음.",
  "evidence": [
    {
      "path": "evidence/image/trivy.json",
      "sha256": "3055f7808775b8179ec9348e5939e208b7ea929053eaa3487dcfef87d9a15854"
    },
    {
      "path": "evidence/image/trivy-gate.txt",
      "sha256": "6f0caae9184f961d08ced658641501401d6af09597d90a3880ab9670acc34145"
    }
  ],
  "policy_name": "HIGH/CRITICAL 이미지 취약점 관리",
  "isms_p": [
    {
      "id": "2.10.8",
      "name": "패치관리"
    },
    {
      "id": "2.11.2",
      "name": "취약점 점검 및 조치"
    }
  ],
  "violations": [],
  "remediation_executed": false,
  "remediation_method": null,
  "before": null,
  "after": null,
  "revalidation": "NOT_TESTED",
  "duration_seconds": null
}
```

## IMG-001 — HIGH/CRITICAL 이미지 취약점 관리

결과: **PASS** · 검증 범위: **local**

통제: 2.10.8 패치관리, 2.11.2 취약점 점검 및 조치

```json
{
  "policy_id": "IMG-001",
  "target": "Trivy 취약 이미지 거부",
  "tool": "Trivy 취약 이미지 거부",
  "scope": "local",
  "result": "PASS",
  "details": "검사 전용 alpine:3.12.0, HIGH/CRITICAL 36건, 실제 프로세스 종료코드1. 실행·배포하지 않음.",
  "evidence": [
    {
      "path": "evidence/vulnerable-control/gate.json",
      "sha256": "dbe3075741ef9034f0c913cbac09df473e62d0845ab858762371b39090ccd522"
    },
    {
      "path": "evidence/vulnerable-control/trivy.json",
      "sha256": "9a1aff40c2420551d31ca7886fe887ee51629e09372bd46c6da36bc9309a486f"
    }
  ],
  "policy_name": "HIGH/CRITICAL 이미지 취약점 관리",
  "isms_p": [
    {
      "id": "2.10.8",
      "name": "패치관리"
    },
    {
      "id": "2.11.2",
      "name": "취약점 점검 및 조치"
    }
  ],
  "violations": [],
  "remediation_executed": false,
  "remediation_method": null,
  "before": null,
  "after": null,
  "revalidation": "NOT_TESTED",
  "duration_seconds": null
}
```

## IMG-001 — HIGH/CRITICAL 이미지 취약점 관리

결과: **PASS** · 검증 범위: **local**

통제: 2.10.8 패치관리, 2.11.2 취약점 점검 및 조치

```json
{
  "policy_id": "IMG-001",
  "target": "CycloneDX SBOM",
  "tool": "CycloneDX SBOM",
  "scope": "local",
  "result": "PASS",
  "details": "CycloneDX 1.7, 구성요소 100개. 공식 스키마 검사 및 실제 config digest 연결.",
  "evidence": [
    {
      "path": "evidence/image/sbom.cdx.json",
      "sha256": "6fb9bfee2aeca5d2a2b6f3a7b73fcba0a6efc353dcbd9f9f3a65f5ac3802aca7"
    },
    {
      "path": "evidence/image/sbom-link.json",
      "sha256": "40ab5e35f0eb04c913323a5007d47b9e1718f5f3ce5a54c5de9ac4bdb564bed1"
    }
  ],
  "policy_name": "HIGH/CRITICAL 이미지 취약점 관리",
  "isms_p": [
    {
      "id": "2.10.8",
      "name": "패치관리"
    },
    {
      "id": "2.11.2",
      "name": "취약점 점검 및 조치"
    }
  ],
  "violations": [],
  "remediation_executed": false,
  "remediation_method": null,
  "before": null,
  "after": null,
  "revalidation": "NOT_TESTED",
  "duration_seconds": null
}
```

## IMG-002 — 미서명 이미지 배포 제한

결과: **PASS** · 검증 범위: **local**

통제: 2.9.1 변경관리, 2.10.2 클라우드 보안

```json
{
  "policy_id": "IMG-002",
  "target": "cosign 로컬 서명",
  "tool": "cosign 로컬 서명",
  "scope": "local",
  "result": "PASS",
  "details": "실제 OCI 레지스트리 서명·정상키 검증·다른키 거부. 테스트 키/tlog 비활성. AWS OIDC/keyless 검증 아님.",
  "evidence": [
    {
      "path": "evidence/local-signature/verify.json",
      "sha256": "02e8a4359af0ffa50d6ea2887622cf5c3b72063a3379619393701dd2a6e77fc1"
    },
    {
      "path": "evidence/local-signature/wrong-key.txt",
      "sha256": "e5bd96e55b6367e0b27a3a95a3e6e051edae831d37f565874657fb5ace8e4575"
    },
    {
      "path": "evidence/local-signature/signed-image.txt",
      "sha256": "281ebe2bcf1d92b55a5a2ff3ec73ccf4ddbbaf68d2b9a7f743fcbdf08e274f17"
    }
  ],
  "policy_name": "미서명 이미지 배포 제한",
  "isms_p": [
    {
      "id": "2.9.1",
      "name": "변경관리"
    },
    {
      "id": "2.10.2",
      "name": "클라우드 보안"
    }
  ],
  "violations": [],
  "remediation_executed": false,
  "remediation_method": null,
  "before": null,
  "after": null,
  "revalidation": "NOT_TESTED",
  "duration_seconds": null
}
```

## NET-002 — 비인가 Pod 접근 차단

결과: **PASS** · 검증 범위: **local**

통제: 2.6.1 네트워크 접근, 2.9.1 변경관리

```json
{
  "policy_id": "NET-002",
  "target": "NetworkPolicy",
  "tool": "NetworkPolicy",
  "scope": "local",
  "result": "PASS",
  "details": "실제 DNS, client→server, 독립 ingress/egress 차단 및 양방향 허용 대조군.",
  "evidence": [
    {
      "path": "evidence/network-kind-team4.log",
      "sha256": "3675cb25302cec2a313f05de6be5c657e12f1bb3c5d590937c2530ea4cf3eae2"
    },
    {
      "path": "evidence/network-kind-team4.json",
      "sha256": "5662a840ac2dc3d08581b5d8f416d5eaaa14aa6e704c466ea94297342c084948"
    }
  ],
  "policy_name": "비인가 Pod 접근 차단",
  "isms_p": [
    {
      "id": "2.6.1",
      "name": "네트워크 접근"
    },
    {
      "id": "2.9.1",
      "name": "변경관리"
    }
  ],
  "violations": [],
  "remediation_executed": false,
  "remediation_method": null,
  "before": null,
  "after": null,
  "revalidation": "NOT_TESTED",
  "duration_seconds": null
}
```

## SEC-001 — 비밀정보 및 접근권한 관리

결과: **PASS** · 검증 범위: **local**

통제: 2.10.2 클라우드 보안

```json
{
  "policy_id": "SEC-001",
  "target": "ESO Fake/rotation",
  "tool": "ESO Fake/rotation",
  "scope": "local",
  "result": "PASS",
  "details": "Kubernetes Secret와 실행중 Pod 볼륨의 값 변화 확인. 원문 출력 없음. AWS SM 검증 아님.",
  "evidence": [
    {
      "path": "evidence/eso-kind-team4.log",
      "sha256": "9cb97ea1872faa9b05e35fd9fd07235290876fbc2610c38b9e2597cb582e51ef"
    }
  ],
  "policy_name": "비밀정보 및 접근권한 관리",
  "isms_p": [
    {
      "id": "2.10.2",
      "name": "클라우드 보안"
    }
  ],
  "violations": [],
  "remediation_executed": false,
  "remediation_method": null,
  "before": null,
  "after": null,
  "revalidation": "NOT_TESTED",
  "duration_seconds": null
}
```

## IMG-002 — 미서명 이미지 배포 제한

결과: **PASS** · 검증 범위: **local**

통제: 2.9.1 변경관리, 2.10.2 클라우드 보안

```json
{
  "policy_id": "IMG-002",
  "target": "Kyverno admission",
  "tool": "Kyverno admission",
  "scope": "local",
  "result": "PASS",
  "details": "정상 Pod 허용 및 잘못된 보안 컨텍스트의 실제 webhook 거부. ECR 서명 정책은 별도 검증 필요.",
  "evidence": [
    {
      "path": "evidence/admission-kind-team4.json",
      "sha256": "59a14963bb6e4e942cbea769d6017d7e689861fb97e7b05df73d54223b6ed6fb"
    },
    {
      "path": "evidence/admission-kind-team4.log",
      "sha256": "504718720761c962eebfa610623a87148ae885a4273f31f8e6cbd216cfa2ce2a"
    }
  ],
  "policy_name": "미서명 이미지 배포 제한",
  "isms_p": [
    {
      "id": "2.9.1",
      "name": "변경관리"
    },
    {
      "id": "2.10.2",
      "name": "클라우드 보안"
    }
  ],
  "violations": [],
  "remediation_executed": false,
  "remediation_method": null,
  "before": null,
  "after": null,
  "revalidation": "NOT_TESTED",
  "duration_seconds": null
}
```

## NET-002 — 비인가 Pod 접근 차단

결과: **PASS** · 검증 범위: **local**

통제: 2.6.1 네트워크 접근, 2.9.1 변경관리

```json
{
  "policy_id": "NET-002",
  "target": "Argo CD GitOps 복구",
  "tool": "Argo CD GitOps 복구",
  "scope": "local",
  "result": "PASS",
  "details": "Git commit 기준 drift 감지→컨트롤러 복구→통신 재검증. admission과 구분.",
  "evidence": [
    {
      "path": "evidence/gitops-kind-team4.json",
      "sha256": "fffae0339a399af6686e9f425a9685903297a943dd5c86a8a1d636d042811704"
    },
    {
      "path": "evidence/gitops-kind-team4.log",
      "sha256": "85f09e8cdb6ccddf3d8216c55533f052f50cb3fdf1900580ccd9dd7a34c5e167"
    }
  ],
  "violations": [
    "demo/allow-client-to-server ingress removed by the local test"
  ],
  "remediation_executed": true,
  "remediation_method": "Argo CD automated selfHeal from the pinned local Git mirror",
  "before": {
    "podSelector": {
      "matchLabels": {
        "app": "server"
      }
    },
    "policyTypes": [
      "Ingress"
    ]
  },
  "after": {
    "ingress": [
      {
        "from": [
          {
            "podSelector": {
              "matchLabels": {
                "app": "client"
              }
            }
          }
        ],
        "ports": [
          {
            "port": 8080,
            "protocol": "TCP"
          }
        ]
      }
    ],
    "podSelector": {
      "matchLabels": {
        "app": "server"
      }
    },
    "policyTypes": [
      "Ingress"
    ]
  },
  "revalidation": "PASS",
  "duration_seconds": 4.941,
  "source_commit": "ba6babcf4b06d340ee79292830cfd1ae576b06b3",
  "policy_name": "비인가 Pod 접근 차단",
  "isms_p": [
    {
      "id": "2.6.1",
      "name": "네트워크 접근"
    },
    {
      "id": "2.9.1",
      "name": "변경관리"
    }
  ]
}
```

## OPS-001 — 로그 및 변경 증적 보존

결과: **PASS** · 검증 범위: **github**

통제: 2.9.1 변경관리, 2.9.4 로그 및 접속기록 관리

```json
{
  "policy_id": "OPS-001",
  "target": "GitHub Actions CI",
  "tool": "GitHub Actions CI",
  "scope": "github",
  "result": "PASS",
  "details": "실제 원격 커밋의 실행 결과. 로컬 스크립트 실행을 CI 성공으로 대체하지 않음. 커밋 `17d88b79186bd9667063c27233aabfb3d1312053` · [실행](https://github.com/realthoroughbred/capstone_1/actions/runs/39117480292).",
  "evidence": [
    {
      "path": "evidence/github/runs-17d88b79186bd9667063c27233aabfb3d1312053.json",
      "sha256": "80ea6e74e1f2a60f7e20a0d93eb45c992f34e27d45b5f7480564ddf9431d1890"
    }
  ],
  "policy_name": "로그 및 변경 증적 보존",
  "isms_p": [
    {
      "id": "2.9.1",
      "name": "변경관리"
    },
    {
      "id": "2.9.4",
      "name": "로그 및 접속기록 관리"
    }
  ],
  "violations": [],
  "remediation_executed": false,
  "remediation_method": null,
  "before": null,
  "after": null,
  "revalidation": "NOT_TESTED",
  "duration_seconds": null
}
```

## OPS-001 — 로그 및 변경 증적 보존

결과: **PASS** · 검증 범위: **aws**

통제: 2.9.1 변경관리, 2.9.4 로그 및 접속기록 관리

```json
{
  "policy_id": "OPS-001",
  "target": "AWS 신원·기존 자원 조회",
  "tool": "AWS 신원·기존 자원 조회",
  "scope": "aws",
  "result": "PASS",
  "details": "team4 프로필, 계정 852093844554. STS 및 EKS·VPC·ECR·Config·OIDC 읽기 전용 조회.",
  "evidence": [
    {
      "path": "evidence/aws/preflight.json",
      "sha256": "7b09236359fd62fe23a6e6ee5fe24a1b393834b4ddee1a881a10ca8d0de7caef"
    }
  ],
  "policy_name": "로그 및 변경 증적 보존",
  "isms_p": [
    {
      "id": "2.9.1",
      "name": "변경관리"
    },
    {
      "id": "2.9.4",
      "name": "로그 및 접속기록 관리"
    }
  ],
  "violations": [],
  "remediation_executed": false,
  "remediation_method": null,
  "before": null,
  "after": null,
  "revalidation": "NOT_TESTED",
  "duration_seconds": null
}
```

## IAC-001 — 인프라 보안 형상 검사

결과: **PASS** · 검증 범위: **aws**

통제: 2.10.2 클라우드 보안, 2.11.2 취약점 점검 및 조치

```json
{
  "policy_id": "IAC-001",
  "target": "AWS Terraform plan",
  "tool": "AWS Terraform plan",
  "scope": "aws",
  "result": "PASS",
  "details": "실제 AWS provider 계획: {'add': 67, 'change': 0, 'destroy': 0}. apply 미실행. docs/AWS_PLAN_REVIEW.md 참고.",
  "evidence": [
    {
      "path": "evidence/aws/plan-summary.json",
      "sha256": "1b07cda481c74c02f3cdcdefbe7ff59e5078d7fc01c4039dcd6a373d49970123"
    },
    {
      "path": "evidence/aws/demo-plan.txt",
      "sha256": "87a58d9beba2e7e40ea38ea6df319d112149ba6f32c31bbde530a0b78e18b0ea"
    }
  ],
  "policy_name": "인프라 보안 형상 검사",
  "isms_p": [
    {
      "id": "2.10.2",
      "name": "클라우드 보안"
    },
    {
      "id": "2.11.2",
      "name": "취약점 점검 및 조치"
    }
  ],
  "violations": [],
  "remediation_executed": false,
  "remediation_method": null,
  "before": null,
  "after": null,
  "revalidation": "NOT_TESTED",
  "duration_seconds": null
}
```

## NET-001 — 공개 SSH 접근 금지

결과: **BLOCKED** · 검증 범위: **aws**

통제: 2.6.1 네트워크 접근, 2.10.2 클라우드 보안, 2.9.4 로그 및 접속기록 관리

```json
{
  "policy_id": "NET-001",
  "target": "AWS plan/ECR/EKS/Config/Inspector",
  "tool": "AWS plan/ECR/EKS/Config/Inspector",
  "scope": "aws",
  "result": "BLOCKED",
  "details": "실제 plan 완료. 정확한 범위의 배포 IAM 준비 및 유료 생성 승인 대기.",
  "evidence": [
    {
      "path": "evidence/aws/preflight.json",
      "sha256": "7b09236359fd62fe23a6e6ee5fe24a1b393834b4ddee1a881a10ca8d0de7caef"
    }
  ],
  "policy_name": "공개 SSH 접근 금지",
  "isms_p": [
    {
      "id": "2.6.1",
      "name": "네트워크 접근"
    },
    {
      "id": "2.10.2",
      "name": "클라우드 보안"
    },
    {
      "id": "2.9.4",
      "name": "로그 및 접속기록 관리"
    }
  ],
  "violations": [],
  "remediation_executed": false,
  "remediation_method": null,
  "before": null,
  "after": null,
  "revalidation": "NOT_TESTED",
  "duration_seconds": null
}
```
