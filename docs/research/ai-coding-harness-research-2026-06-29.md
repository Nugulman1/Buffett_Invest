# 코딩 고수 설정·"제2의 나"·개발 자동화 — 딥리서치 종합

> 작성일: 2026-06-29
> 방법: deep-research 워크플로(5단계: 범위분해→병렬검색→소스수집→적대검증→종합).
> 통계: 소스 21개 수집, 주장 104개 추출, 25개 적대검증 → **24개 확정 / 1개 기각**.
> ⚠️ 워크플로의 종합 단계가 버그로 플레이스홀더를 반환 → 검증된 원자료로 직접 재종합함.
> 신뢰도 표기: **확정**(2~3표 적대검증 통과), ⚠️**미검증**(블로그 단일출처, 적대검증 미통과).

---

## 한 줄 결론

- **"제2의 나"의 핵심은 CLAUDE.md에 취향을 *선언*하는 게 아니라 교정을 *누적*시키는 것**(Compounding Engineering).
- **"완전 자동화"의 천장은 실행이 아니라 검증.** 에이전트는 자기 성공을 체계적으로 과신함(실제 22~35% vs 자기예측 73~77%).

---

## 각도 1 — CLAUDE.md·서브에이전트 베스트 프랙티스 (공식 + 실무)

- **서브에이전트 = 격리 컨텍스트 + 전용 시스템프롬프트 + 제한된 툴 권한.** Markdown+YAML frontmatter로 정의, body가 곧 시스템프롬프트, 필수 필드는 `name`/`description`뿐. 메인엔 요약만 반환 → 컨텍스트 보존. **[확정 3-0]** — `code.claude.com/docs/en/sub-agents`
- **CLAUDE.md = 복리식 오류교정 장치(Compounding Engineering).** "Claude가 틀릴 때마다 CLAUDE.md에 추가". **[확정 3-0]** — `support.claude.com/.../14554000`
- **핵심 규칙은 CLAUDE.md로 올려라 — compaction(컨텍스트 압축)에도 살아남음.** 대화이력은 요약돼 사라지지만 CLAUDE.md는 매 세션·매 compact마다 재주입. **[확정 3-0]**
- **자율 루프는 자기평가가 아니라 외부 검증자(테스트 스위트)로 완료 판정해야 함.** **[확정, central]** — `mindstudio.ai/blog/how-to-build-agentic-loop-claude-code`
- **`/loop`(로컬 최대 3일)·`/schedule`(클라우드, 기기 꺼져도 실행)** 으로 자율 루프·클라우드 스케줄링. **[확정 3-0]**
- ⚠️ **"CLAUDE.md는 팀 공유 단일 파일이 정석" — 2-1 통과, 반대표 존재**: 같은 벤더 공식문서의 다층(전역/프로젝트/중첩) 구조와 충돌. 단일파일 절대시 금지.
- ⚠️ (블로그) 프런티어 LLM은 ~150-200개 지시만 안정적으로 따르고 시스템프롬프트가 ~50개 소모 → CLAUDE.md는 ~200줄 이하 유지. 미검증, 참고용.

## 각도 2 — 고수들의 실전 설정 레포 (바로 훔쳐볼 자료)

- **`github.com/wshobson/agents`** — 88 plugins, 194 agents, 158 skills, 106 commands. **단일 Markdown 소스가 Claude Code·Codex CLI·Cursor·Gemini CLI·Copilot에서 그대로 동작.** **[확정 3-0, git tree 독립검증]**
- **wshobson 계층형 모델 전략**: Tier1 Opus(아키텍처·보안·코드리뷰·프로덕션), Tier3 Sonnet(문서·테스트·디버깅), Tier4 Haiku(빠른 운영). **[확정 3-0]**
- **`github.com/VoltAgent/awesome-claude-code-subagents`** — 154+ 서브에이전트, 10개 카테고리. **[확정 3-0]**
- **`github.com/zhsama/claude-sub-agent`** — 다단계 워크플로를 **수치 품질게이트로 강제**: Planning 95% / Development 80% / Validation 85%, 미달 시 이전 에이전트로 자동 회귀. **[확정 3-0]**

## 각도 3 — "제2의 나" / 페르소나 주입 방법론 ⚠️ 신뢰도 낮음

> 이 각도는 블로그 단일출처 + 적대검증 미통과(예산상 25/104만 검증). 아이디어 참고용.

- **Zakas(humanwhocodes)**: AI를 단일 비서가 아닌 **6개 페르소나로 분해**(PM·아키텍트·구현자·문제해결사·스펙리뷰어·구현리뷰어), 각자 프롬프트+모델 배정. ⚠️미검증
- **"Developer Digital Twin"**(keyholesoftware): 잘 구조화된 입력(유저스토리+행동테스트)이면 전형적 개발작업 **~80%**를 5~15분에 처리. ⚠️미검증
- 페르소나를 전역 `~/.claude/CLAUDE.md`와 프로젝트 단위 두 층에 주입. ⚠️미검증

## 각도 4 — 하네스 엔지니어링 / 자율 루프 최신

- **하네스 엔지니어링 정의**: 모델을 둘러싼 스캐폴딩(컨텍스트 전달·툴 인터페이스·계획 산출물·검증 루프·메모리·샌드박스) 설계. "모델이 혼자 못 하니 존재, 모델이 좋아지면 사라질 운명." **[확정 3-0]** — `github.com/ai-boost/awesome-harness-engineering`
- **OpenAI 실험**: 5개월간 **수작업 코드 0줄로 ~100만 LOC 베타 제품 출시**, 엔지니어 3명이 ~1,500 PR 머지, Codex 6시간 연속 자율작업. **[확정 3-0, 단 자기홍보성 n=1]** — `openai.com/index/harness-engineering`
- **Codex 자기검증 루프**: 자기 변경 로컬 리뷰→추가 에이전트 리뷰 요청→피드백 반영→모든 리뷰어 만족까지 반복. **[확정 3-0]**
- **AHE 논문(arXiv 2604.25850)**: 하네스 자동진화 10회로 Terminal-Bench 2 pass@1 **69.7%→77.0%**, 사람설계 능가. 단 **장기메모리 단독 +5.6pp, 시스템프롬프트 단독 -2.3pp(역효과)** — 컴포넌트 공진화가 핵심. 저자도 "연구 프로토타입"이라 명시. **[확정 3-0]**

## 각도 5 — 자동화의 한계 (핵심 반론)

- **프런티어 에이전트는 체계적으로 과신**(arXiv 2602.06948): SWE-bench Pro 100태스크 실제 성공률 GPT-5.2-Codex 35%·Gemini-3-Pro 22%·Opus 4.5 27%, 그러나 **자기예측 성공률 73%**. **[확정 3-0]**
- **사후 자기리뷰로는 과신이 안 고쳐진다.** **[확정 3-0]**
- **"correctness 검증"이 아니라 "버그를 찾아라"로 프레임 전환 시 과신 최대 15pp 감소.** **[확정 3-0]**
- 톱 에이전트도 SWE-bench-verified에서 **65~76.8%**만 해결(잘 정의된 과제의 ~1/4 실패). Anthropic 자체 엔지니어도 **80~100% 태스크에 인간 감독 유지.** ⚠️(blog/swarmia)

---

## 기각된 주장 (정직성)

- ✗ **"자율코딩의 진짜 병목은 모델 능력이 아니라 '환경 가독성(environment legibility)'이다"** — **2:1 기각**. 사유: OpenAI 자기홍보 블로그(n=1, 엔지니어 3명) 검증 불가 주장, 인용문 미확인(HTTP 403). *핵심 취지(환경 미명세가 초기 병목)는 인정되나 일반화는 과함.*

---

## 시사점 (내 프로젝트 적용)

1. **"훔쳐보기"는 그릇만**: wshobson·VoltAgent·zhsama에서 *구조*(계층모델·품질게이트·페르소나분할)를 가져오되 내용물은 내 교정에서. 이미 메모리 feedback = Compounding Engineering 실행 중.
2. **auto-loop 보강 2개**: (a) zhsama식 **수치 품질게이트 + 자동회귀**, (b) 검증 프롬프트를 "맞는지 확인"→**"버그를 찾아라"로 전환**(과신 -15pp, 실증).
3. **"완전 자동화" 답**: 실행은 6시간 자율도 가능. 그러나 에이전트 과신(실제 27% vs 예측 73%)이 구조적 → **독립 검증 + 인간 오케스트레이션이 천장**.

---

## 전체 소스 21개 (품질·각도 태그)

### 각도 1 — CLAUDE.md 베스트 프랙티스
1. `code.claude.com/docs/en/sub-agents` — **primary** (공식 docs)
2. `alexop.dev/posts/claude-code-customization-guide-claudemd-skills-subagents/` — blog
3. `support.claude.com/en/articles/14554000-claude-code-power-user-tips` — **primary**
4. `dev.to/monuminu/inside-the-agentic-loop-a-deep-technical-dive-into-ai-coding-agents-claude-code-and-the-4pnf` — blog
5. `mindstudio.ai/blog/how-to-build-agentic-loop-claude-code` — blog
6. `dev.to/mir_mursalin_ankur/claude-code-configuration-blueprint-the-complete-guide-for-production-teams-557p` — blog

### 각도 2 — 실전 설정 모음
7. `github.com/VoltAgent/awesome-claude-code-subagents` — secondary
8. `github.com/wshobson/agents` — **primary**
9. `github.com/zhsama/claude-sub-agent` — **primary**

### 각도 3 — "제2의 나" 방법론
10. `humanwhocodes.com/blog/2025/06/persona-based-approach-ai-assisted-programming/` — blog (Zakas)
11. `keyholesoftware.com/developer-digital-twin-with-agentic-ai-and-what-it-got-right-wrong/` — blog
12. `dev.to/abduarrahman/why-i-gave-my-ai-coding-assistant-a-personality-persona-in-claudemd-16o0` — blog

### 각도 4 — 하네스 엔지니어링 / 자율 루프
13. `openai.com/index/harness-engineering/` — secondary (OpenAI 자기홍보)
14. `github.com/ai-boost/awesome-harness-engineering` — secondary
15. `augmentcode.com/guides/harness-engineering-ai-coding-agents` — secondary
16. `arxiv.org/html/2604.25850v1` — **primary** (AHE 논문)
17. `swarmia.com/blog/five-levels-ai-agent-autonomy/` — blog
18. `puppyone.ai/en/blog/what-is-loop-engineering-5-building-blocks-missing-one` — blog

### 각도 5 — 자동화의 한계
19. `mikemason.ca/writing/ai-coding-agents-jan-2026/` — blog
20. `finkletech.com/ai-coding-agents-reliability-problem/` — blog
21. `arxiv.org/pdf/2602.06948` — **primary** (Agentic Overconfidence 논문)
