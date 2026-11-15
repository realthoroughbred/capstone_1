# 최종 코드 커밋의 실제 GitHub CI 결과

- 소스 commit: `0ccf02ceee88b8c4a82c694d0cee78809b8f252d`.
- [run 43763799295](https://github.com/realthoroughbred/capstone_1/actions/runs/43763799295), 2026-11-16 KST.
- image 성공: 빌드·Trivy 17 packages/발견 0·SBOM 100 components·로컬 암호학적 서명/다른 키 거부.
- validate 실패: 단위 161개·Terraform mock 10개는 성공, **Checkov 131통과·3실패·23생략**으로 종료 1.
- risk-report 실패 표시: 보고서 프로그램은 정상 작성했고 **INCOMPLETE/종료 2**. Checkov PARTIAL/gate FAILED, Trivy COMPLETE/gate PASSED. 두 scanner의 commit/run/tree hash 일치와 원본 hash를 확인했으며 보고서의 출처 불일치 목록은 비어 있다.

이 결과는 전체 CI 성공이 아니다. 새 시험용 S3의 접근 로그·교차 리전 복제·이벤트 알림이 실패이고, 생략 23개도 안전 판정 대상에 포함하지 않았다. [조치 검토표](SECURITY_DISPOSITION.md)를 따른다.

로컬 Checkov **184/3/23**과 원격 **131/3/23**을 합산하지 않는다. 로컬에는 Git 제외 변수 파일 등 다른 입력 환경이 있고, 같은 도구 버전이라도 결과 집합은 다르다. 이번에는 원격 원본 artifact를 보고서에 직접 연결했다. 정확한 pass 항목 차이의 전체 원인 분석은 미완료이며 어느 쪽 수치로 다른 쪽 결과를 보정하지 않았다.

CI image config digest: `sha256:64dfcab51682beb76da680e551952e3f7090719a0b83185663f079905ccd1b4b`. 이 값은 별도의 로컬 수정 이미지 config digest와 다르다. AWS ECR manifest digest/승인 safe image가 아니다.

원본은 [run별 폴더](../evidence/finalization-20261116/github-43763799295/)에 GitHub artifact ZIP 그대로 저장했다. 공개된 SHA256과 다운로드 bytes를 대조한 뒤 내용을 풀었다. [job 원본 로그](../evidence/finalization-20261116/github-logs-43763799295/), [실제 위험 보고서](../evidence/finalization-20261116/github-43763799295/isms-p-risk-report/isms-p-risk-report.md)를 함께 본다. artifact는 2026-11-29 만료 예정이므로 로컬 사본을 보존한다.

## 원본 artifact 무결성

| artifact | SHA256 |
|---|---|
| static-and-unit-evidence | `sha256:db9520ab6d202681152175581ab6011b2c9b12aac3204abac64c000aee565452` |
| isms-p-risk-report | `sha256:ce0775329b697749f101fbd1fe1a11f66d63210f9f1ff4b4c39ac9ea87ca7c0f` |
| image-security-evidence | `sha256:bbb39f0b23ec822df8973b1d91dd04a2ecdbbb29a288cc7060d000240f73816b` |

이후 CI 관측 기록·WBS 경로만 보완한 문서 커밋은 위 코드 commit의 시험 결과를 그대로 가리킨다. 코드·정책·CI 설정을 바꾸지 않는 기록 추가로 중복 빌드/검사를 실행하지 않는다.
