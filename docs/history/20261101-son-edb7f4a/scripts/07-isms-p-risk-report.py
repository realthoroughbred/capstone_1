import json
from pathlib import Path
from datetime import datetime
from collections import Counter

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "reports/checkov.json"
OUTPUT = ROOT / "reports/isms-p-risk-report.md"

# 프로젝트 내부 초기 위험도 기준
# 형식: (ISMS-P 통제번호, 발생 가능성, 영향도, 개선 방안)
RULES = {
    "CKV_AWS_394": ("2.8.1", 2, 2, "가용영역 식별자 고정 검토"),
    "CKV_AWS_130": ("2.6.1", 3, 4, "퍼블릭 IP 자동 할당 필요성 검토"),
    "CKV_AWS_338": ("2.9.4", 3, 4, "로그 보존기간 365일 이상 검토"),
    "CKV_AWS_158": ("2.7.2", 3, 4, "CloudWatch KMS 암호화 적용"),
    "CKV_AWS_39": ("2.6.1", 3, 5, "EKS 엔드포인트 접근 범위 제한 검증"),
    "CKV_AWS_58": ("2.7.2", 3, 5, "EKS Secrets 암호화 설정"),
    "CKV_AWS_37": ("2.9.4", 4, 4, "EKS Control Plane 로그 활성화"),
    "CKV_AWS_136": ("2.7.2", 3, 4, "ECR KMS 암호화 적용 검토"),
    "CKV2_AWS_12": ("2.6.1", 4, 5, "기본 보안 그룹 트래픽 제한 검증"),
    "CKV2_AWS_11": ("2.10.2", 3, 4, "VPC Flow Logs 활성화 검토"),
    "CKV2_AWS_5": ("2.8.1", 2, 2, "보안 그룹 연결 여부 확인"),
}

# 실습 설계상 예외 가능성이 있으나 자동 승인하지 않음
EXCEPTION_CANDIDATES = {"CKV_AWS_130", "CKV_AWS_39"}

def escape(value):
    return str(value or "-").replace("|", "\\|").replace("\n", " ")

def grade(score):
    if score >= 15:
        return "상"
    if score >= 8:
        return "중"
    return "하"

if not SOURCE.exists():
    raise SystemExit(f"검사 결과 파일 없음: {SOURCE}")

data = json.loads(SOURCE.read_text(encoding="utf-8"))
reports = data if isinstance(data, list) else [data]

findings = []
passed = 0

for report in reports:
    summary = report.get("summary", {})
    passed += summary.get("passed", 0)

    for check in report.get("results", {}).get("failed_checks", []):
        check_id = check.get("check_id", "UNKNOWN")
        resource = check.get("resource", "-")

        if check_id in RULES:
            control, likelihood, impact, action = RULES[check_id]
            score = likelihood * impact
            level = grade(score)
        else:
            control, likelihood, impact = "검토 필요", None, None
            score, level = None, "미평가"
            action = "신규 검사 규칙의 위험도 및 통제항목 검토"

        findings.append({
            "id": check_id,
            "name": check.get("check_name", "-"),
            "resource": resource,
            "control": control,
            "likelihood": likelihood,
            "impact": impact,
            "score": score,
            "level": level,
            "action": action,
            "status": (
                "예외 검토 후보"
                if check_id in EXCEPTION_CANDIDATES
                else "조치 검토"
            ),
        })

findings.sort(key=lambda x: (-(x["score"] or 0), x["id"]))
counts = Counter(f["level"] for f in findings)

lines = [
    "# ISMS-P 위험도 평가 자동화 보고서",
    "",
    f"- 생성일시: {datetime.now().astimezone():%Y-%m-%d %H:%M:%S %Z}",
    "- 분석 대상: Terraform IaC (infra/)",
    "- 분석 도구: Checkov 3.3.29",
    "- 평가 범위: 로컬 정적 분석 결과",
    "- 평가 상태: 초기 위험도 산정 / 담당자 검토 필요",
    "",
    "## 1. 검사 결과",
    "",
    f"- 통과: {passed}건",
    f"- 실패: {len(findings)}건",
    f"- 실패 규칙 종류: {len(set(f['id'] for f in findings))}종",
    "",
    "## 2. 위험도 평가 기준",
    "",
    "- 위험점수 = 발생 가능성(1~5) × 영향도(1~5)",
    "- 상: 15~25점 / 중: 8~14점 / 하: 1~7점",
    "- 점수는 프로젝트 내부 초기 평가값이며 공식 Checkov 심각도가 아님",
    "- 실제 적용 환경과 보완통제 확인 후 최종 평가 필요",
    "",
    "## 3. 위험등급별 현황",
    "",
]

for level in ["상", "중", "하", "미평가"]:
    lines.append(f"- {level}: {counts[level]}건")

lines += [
    "",
    "## 4. 취약점별 위험도 평가",
    "",
    "| 검사 ID | 대상 리소스 | ISMS-P | 가능성 | 영향도 | 점수 | 등급 | 상태 |",
    "|---|---|---|---:|---:|---:|---|---|",
]

for f in findings:
    lines.append(
        f"| {escape(f['id'])} | {escape(f['resource'])} | "
        f"{f['control']} | {f['likelihood'] or '-'} | "
        f"{f['impact'] or '-'} | {f['score'] or '-'} | "
        f"{f['level']} | {f['status']} |"
    )

lines += [
    "",
    "## 5. 조치 권고 및 예외 검토",
    "",
]

for i, f in enumerate(findings, 1):
    lines += [
        f"### {i}. {f['id']}",
        "",
        f"- 검사 내용: {f['name']}",
        f"- 대상: {f['resource']}",
        f"- 초기 위험등급: {f['level']}",
        f"- 개선 방안: {f['action']}",
        f"- 처리 상태: {f['status']}",
        "",
    ]

lines += [
    "## 6. 평가 한계 및 후속 작업",
    "",
    "- 본 결과는 미배포 Terraform 코드의 정적 검사 결과임",
    "- 예외 후보는 담당자 검토 및 승인 전까지 위반 항목으로 유지",
    "- ISMS-P 매핑은 프로젝트 내부 기준이며 통제항목 적합성 검토 필요",
    "- 실제 AWS/EKS 적용 후 보완통제 및 운영 증적 재검증 필요",
    "",
]


# BEGIN TRIVY INTEGRATION
TRIVY_SOURCE = ROOT / "reports/trivy.json"

lines += [
    "",
    "## 7. Trivy 이미지 취약점 위험도 평가",
    "",
    "- ISMS-P 매핑: 2.8.2 보안 테스트, 2.11.2 취약점 점검 및 조치",
    "- 평가 기준: 프로젝트 내부 초기 위험도 기준",
    "",
]

if TRIVY_SOURCE.exists():
    trivy_data = json.loads(
        TRIVY_SOURCE.read_text(encoding="utf-8")
    )

    vulnerabilities = [
        v
        for result in trivy_data.get("Results", [])
        for v in (result.get("Vulnerabilities") or [])
        if v.get("Severity") in ("HIGH", "CRITICAL")
    ]

    critical = sum(
        v.get("Severity") == "CRITICAL"
        for v in vulnerabilities
    )
    high = sum(
        v.get("Severity") == "HIGH"
        for v in vulnerabilities
    )

    lines += [
        f"- CRITICAL: {critical}건",
        f"- HIGH: {high}건",
        f"- 합계: {len(vulnerabilities)}건",
        "",
    ]

    if vulnerabilities:
        lines += [
            "| CVE | 패키지 | 심각도 | 가능성 | 영향도 | 위험점수 | 등급 |",
            "|---|---|---|---:|---:|---:|---|",
        ]

        for v in vulnerabilities:
            severity = v["Severity"]
            likelihood, impact = (
                (4, 5) if severity == "CRITICAL" else (3, 4)
            )
            score = likelihood * impact

            lines.append(
                f"| {escape(v.get('VulnerabilityID'))} "
                f"| {escape(v.get('PkgName'))} "
                f"| {severity} | {likelihood} | {impact} "
                f"| {score} | {grade(score)} |"
            )

        lines += [
            "",
            "- 위 점수는 심각도 기반의 초기 가정이며 실제 위험도 검토가 필요함.",
        ]
    else:
        lines += [
            "검사한 이미지에서 HIGH/CRITICAL 취약점이 발견되지 않았습니다.",
            "",
        ]
else:
    lines += [
        "Trivy 검사 결과 파일이 없어 평가하지 않았습니다.",
        "",
    ]
# END TRIVY INTEGRATION

OUTPUT.parent.mkdir(parents=True, exist_ok=True)
OUTPUT.write_text("\n".join(lines), encoding="utf-8")

print("===== ISMS-P 자동 위험도 평가 =====")
print(f"통과: {passed}건")
print(f"실패: {len(findings)}건")
for level in ["상", "중", "하", "미평가"]:
    print(f"위험도 {level}: {counts[level]}건")
print(f"보고서 생성: {OUTPUT}")
