# Diagnostics

## Audit checkpoint 2026-05-10

Continuation prompt scope: audit first, fix only P0/P1 regressions, preserve slash commands, callback data, Telegram Stars payloads, Crypto Pay payloads and invite/subscription runtime contracts.

Current runtime baseline:

- Entry point is `app.main`; it creates the SQLAlchemy async engine/session factory, seeds managed texts, starts background workers and then runs either polling or aiohttp webhook mode.
- Webhook mode is served by `app.webhook.server`; Telegram webhook rejects invalid `X-Telegram-Bot-Api-Secret-Token`, Crypto Pay webhook validates `crypto-pay-api-signature`, and `/healthz` plus `/readyz` are available.
- Mini App APIs are Telegram `initData`-protected; admin routes are role/permission-gated and now default heavy admin views to snapshot read models with explicit `source`, `generated_at` and `staleness_seconds`.
- Payments remain additive: Stars and Crypto Pay both dedupe by charge/invoice id before extending access, then write payment/audit/referral events inside the same DB session.
- Snapshot wave is partially implemented: `analytics_daily_facts`, `lifecycle_campaign_facts`, `support_queue_facts`, query/payload budgets, lazy admin endpoints and scheduler refresh are present.

Baseline commands run in this checkpoint:

- `python -m compileall .` with bare `python` did not start because `python` is not on PATH in this PowerShell environment.
- Full-path `python -m compileall .` reached `.vendor` / local dependency caches and failed on permission-protected files; this is a root-scope environment issue, not an app syntax failure.
- Production-scope `python -m compileall -q app tests alembic scripts` passed.
- `python -m unittest discover -s tests -p "test_*.py" -v` found 0 tests because the suite is pytest-style.
- `pytest -q -p no:cacheprovider` passed: 351 tests.
- `ruff check app tests alembic` passed.
- `python -m alembic upgrade head` passed on the local SQLite dev database.
- `python -m app.healthcheck` passed.
- `node --check .codex-tmp\miniapp-check.js` passed.
- `python -m app.tools.scan_texts` passed after the P1 encoding fix below.
- Wave 3 support modularization checkpoint passed: targeted support ruff, `python -m compileall -q app`, `python -m app.tools.scan_texts` and `pytest tests/unit/test_support_service.py tests/integration/test_mini_app_runtime.py tests/integration/test_support_runtime.py -q -p no:cacheprovider` all completed green after extracting support DTOs, catalog labels/constants/helpers and canned reply packs.
- Wave 3 support SLA/routing extraction checkpoint passed: targeted support ruff, `python -m compileall -q app`, `python -m app.tools.scan_texts` and `pytest tests/unit/test_support_service.py tests/unit/test_service_module_contracts.py tests/integration/test_mini_app_runtime.py tests/integration/test_support_runtime.py -q -p no:cacheprovider` completed green after moving waiting-state, SLA bucket, action-lane, escalation-lane and next-action helpers into `app.services.support_sla`.
- Wave 3 support ticket-flow extraction checkpoint passed: targeted support ruff, `python -m compileall -q app`, `python -m app.tools.scan_texts` and `pytest tests/unit/test_support_service.py tests/unit/test_service_module_contracts.py tests/integration/test_mini_app_runtime.py tests/integration/test_support_runtime.py -q -p no:cacheprovider` completed green after moving ticket validation, user/admin thread reads and create/reply/close/reopen mutations into `app.services.support_ticket_flow`.
- Wave 3 support closed-insight trends extraction checkpoint passed: targeted support ruff, `python -m compileall -q app` and `pytest tests/unit/test_support_service.py tests/unit/test_service_module_contracts.py tests/integration/test_mini_app_runtime.py tests/integration/test_support_runtime.py -q -p no:cacheprovider` completed green after moving canned-reply pack outcomes, close-reason trends, historical escalation trends and operator action trends into `app.services.support_insight_trends`.
- Wave 3 support open-queue extraction checkpoint passed: targeted support ruff, `python -m compileall -q app` and `pytest tests/unit/test_support_service.py tests/unit/test_service_module_contracts.py tests/integration/test_mini_app_runtime.py tests/integration/test_support_runtime.py -q -p no:cacheprovider` completed green after moving SLA hotspots, action queues, escalation lanes, priority focus, triage queues and sample ticket ordering into `app.services.support_open_queues`.
- Wave 3 support queue-ranking extraction checkpoint passed: targeted support ruff, `python -m compileall -q app` and `pytest tests/unit/test_service_module_contracts.py tests/unit/test_support_service.py tests/integration/test_mini_app_runtime.py tests/integration/test_support_runtime.py -q -p no:cacheprovider` completed green after moving queue rank keys and sample ticket selection helpers into `app.services.support_queue_ranking` with compatibility imports from `app.services.support_open_queues`.
- Wave 3 support SLA queue extraction checkpoint passed: targeted support ruff, `python -m compileall -q app` and `pytest tests/unit/test_service_module_contracts.py tests/unit/test_support_service.py tests/integration/test_mini_app_runtime.py tests/integration/test_support_runtime.py -q -p no:cacheprovider` completed green after moving SLA hotspot, SLA action, SLA action queue, action lane and hotspot-kind builders into `app.services.support_sla_queues` with compatibility imports from `app.services.support_open_queues`.
- Wave 3 support action/triage queue extraction checkpoint passed: targeted support ruff, `python -m compileall -q app` and `pytest tests/unit/test_service_module_contracts.py tests/unit/test_support_service.py tests/integration/test_mini_app_runtime.py tests/integration/test_support_runtime.py -q -p no:cacheprovider` completed green after moving next-action, action-route and triage queue builders into `app.services.support_action_queues` with compatibility imports from `app.services.support_open_queues`.
- Wave 3 support escalation/priority queue extraction checkpoint passed: targeted support ruff, `python -m compileall -q app` and `pytest tests/unit/test_service_module_contracts.py tests/unit/test_support_service.py tests/integration/test_mini_app_runtime.py tests/integration/test_support_runtime.py -q -p no:cacheprovider` completed green after moving escalation lane/action, priority focus and escalation watchlist builders into `app.services.support_escalation_queues` with compatibility imports from `app.services.support_open_queues`.
- Wave 3 support triage-apply extraction checkpoint passed: targeted support ruff, `python -m compileall -q app` and `pytest tests/unit/test_support_service.py tests/unit/test_service_module_contracts.py tests/integration/test_mini_app_runtime.py tests/integration/test_support_runtime.py -q -p no:cacheprovider` completed green after moving recent apply history, route/actor/reply aggregates, focus queues and effectiveness views into `app.services.support_triage_apply`.
- Wave 3 support triage-apply ranking extraction checkpoint passed: targeted support ruff, `python -m compileall -q app` and `pytest tests/unit/test_service_module_contracts.py tests/unit/test_support_service.py tests/integration/test_mini_app_runtime.py tests/integration/test_support_runtime.py -q -p no:cacheprovider` completed green after moving focus/effectiveness ranking builders into `app.services.support_triage_apply_rankings` with compatibility imports from `app.services.support_triage_apply`.
- Wave 3 support triage-apply history extraction checkpoint passed: targeted support ruff, `python -m compileall -q app` and `pytest tests/unit/test_service_module_contracts.py tests/unit/test_support_service.py tests/integration/test_mini_app_runtime.py tests/integration/test_support_runtime.py -q -p no:cacheprovider` completed green after moving triage-apply audit-log loading, JSON payload parsing and actor/reply labeling into `app.services.support_triage_apply_history` with compatibility imports from `app.services.support_triage_apply`.
- Wave 3 support triage-apply note extraction checkpoint passed: targeted support ruff, `python -m compileall -q app` and `pytest tests/unit/test_service_module_contracts.py tests/unit/test_support_service.py tests/integration/test_mini_app_runtime.py tests/integration/test_support_runtime.py -q -p no:cacheprovider` completed green after moving triage-apply aggregate note helpers into `app.services.support_triage_apply_notes` with compatibility imports from `app.services.support_triage_apply`.
- Wave 3 support triage-apply combination extraction checkpoint passed: targeted support ruff, `python -m compileall -q app` and `pytest tests/unit/test_service_module_contracts.py tests/unit/test_support_service.py tests/integration/test_mini_app_runtime.py tests/integration/test_support_runtime.py -q -p no:cacheprovider` completed green after moving reply-pack and route/reply/actor combination aggregate builders into `app.services.support_triage_apply_combinations` with compatibility imports from `app.services.support_triage_apply`.
- Wave 3 support triage-apply core extraction checkpoint passed: targeted support ruff, `python -m compileall -q app` and `pytest tests/unit/test_service_module_contracts.py tests/unit/test_support_service.py tests/integration/test_mini_app_runtime.py tests/integration/test_support_runtime.py -q -p no:cacheprovider` completed green after moving route and actor aggregate builders into `app.services.support_triage_apply_core` with compatibility imports from `app.services.support_triage_apply`.
- Wave 3 support triage-apply reply aggregate extraction checkpoint passed: targeted support ruff, `python -m compileall -q app` and `pytest tests/unit/test_service_module_contracts.py tests/unit/test_support_service.py tests/integration/test_mini_app_runtime.py tests/integration/test_support_runtime.py -q -p no:cacheprovider` completed green after moving reply, actor/reply and route/actor aggregate builders into `app.services.support_triage_apply_replies` with compatibility imports from `app.services.support_triage_apply`.
- Wave 3 support canned-reply builder extraction checkpoint passed: targeted support ruff, `python -m compileall -q app` and `pytest tests/unit/test_support_service.py tests/unit/test_service_module_contracts.py tests/integration/test_mini_app_runtime.py tests/integration/test_support_runtime.py -q -p no:cacheprovider` completed green after moving canned-reply builders into `app.services.support_reply_packs` with compatibility re-exports from `app.services.support`.
- Wave 3 Mini App support action extraction checkpoint passed: targeted support-admin ruff, `python -m compileall -q app` and `pytest tests/unit/test_service_module_contracts.py tests/integration/test_mini_app_runtime.py -q -p no:cacheprovider` completed green after moving support triage confirm/apply token, scope and mutation logic into `app.services.web_admin_dashboard_support_actions` with compatibility re-exports from `app.services.web_admin_dashboard_support_sections`.
- Wave 3 Mini App support ticket-serializer extraction checkpoint passed: targeted support-admin ruff, `python -m compileall -q app` and `pytest tests/unit/test_service_module_contracts.py tests/integration/test_mini_app_runtime.py -q -p no:cacheprovider` completed green after moving support ticket/list/queue serializers and helpers into `app.services.web_admin_dashboard_support_ticket_serializers` with compatibility imports from `app.services.web_admin_dashboard_support_sections`.
- Wave 3 Mini App support insight-serializer extraction checkpoint passed: targeted support-admin ruff, `python -m compileall -q app` and `pytest tests/unit/test_service_module_contracts.py tests/integration/test_mini_app_runtime.py -q -p no:cacheprovider` completed green after moving the large support insights serializer into `app.services.web_admin_dashboard_support_insight_serializers` with compatibility imports from `app.services.web_admin_dashboard_support_sections`.
- Wave 3 Mini App support closed-insight serializer extraction checkpoint passed: targeted support-admin ruff, `python -m compileall -q app` and `pytest tests/unit/test_service_module_contracts.py tests/unit/test_support_service.py tests/integration/test_mini_app_runtime.py tests/integration/test_support_runtime.py -q -p no:cacheprovider` completed green after moving close-reason distribution, close-reason trend and canned-reply pack outcome serializers/summaries into `app.services.web_admin_dashboard_support_closed_insight_serializers` with compatibility imports from `app.services.web_admin_dashboard_support_insight_serializers`.
- Wave 3 Mini App support SLA/action insight serializer extraction checkpoint passed: targeted support-admin ruff, `python -m compileall -q app` and `pytest tests/unit/test_service_module_contracts.py tests/unit/test_support_service.py tests/integration/test_mini_app_runtime.py tests/integration/test_support_runtime.py -q -p no:cacheprovider` completed green after moving SLA hotspot, SLA action, action lane, next-action and action-route serializers/summaries into `app.services.web_admin_dashboard_support_action_insight_serializers` with compatibility imports from `app.services.web_admin_dashboard_support_insight_serializers`.
- Wave 3 Mini App support triage-apply serializer split checkpoint passed: targeted support-admin ruff, `python -m compileall -q app` and `pytest tests/unit/test_service_module_contracts.py tests/unit/test_support_service.py tests/integration/test_mini_app_runtime.py tests/integration/test_support_runtime.py -q -p no:cacheprovider` completed green after moving triage queue/plan/confirm, triage-apply insight view serialization and triage summary payloads into `app.services.web_admin_dashboard_support_triage_apply_serializers` with compatibility imports from `app.services.web_admin_dashboard_support_insight_serializers`.
- Wave 3 Mini App support triage queue serializer extraction checkpoint passed: targeted support-admin ruff, `python -m compileall -q app` and `pytest tests/unit/test_service_module_contracts.py tests/unit/test_support_service.py tests/integration/test_mini_app_runtime.py tests/integration/test_support_runtime.py -q -p no:cacheprovider` completed green after moving triage queue, triage plans and preview-only confirm serializers into `app.services.web_admin_dashboard_support_triage_queue_serializers` with compatibility imports from `app.services.web_admin_dashboard_support_triage_apply_serializers`.
- Wave 3 Mini App support triage-apply view serializer extraction checkpoint passed: targeted support-admin ruff, `python -m compileall -q app` and `pytest tests/unit/test_service_module_contracts.py tests/unit/test_support_service.py tests/integration/test_mini_app_runtime.py tests/integration/test_support_runtime.py -q -p no:cacheprovider` completed green after moving triage-apply history/aggregate/focus/effectiveness list serializers into `app.services.web_admin_dashboard_support_triage_apply_view_serializers` with compatibility imports from `app.services.web_admin_dashboard_support_triage_apply_serializers`.
- Wave 3 Mini App support triage summary serializer extraction checkpoint passed: targeted support-admin ruff, `python -m compileall -q app` and `pytest tests/unit/test_service_module_contracts.py tests/unit/test_support_service.py tests/integration/test_mini_app_runtime.py tests/integration/test_support_runtime.py -q -p no:cacheprovider` completed green after moving triage summary payload builders into `app.services.web_admin_dashboard_support_triage_summary_serializers` with compatibility imports from `app.services.web_admin_dashboard_support_triage_apply_serializers`.
- Wave 3 Mini App support insight view-registry extraction checkpoint passed: targeted support-admin ruff, `python -m compileall -q app` and `pytest tests/unit/test_service_module_contracts.py tests/unit/test_support_service.py tests/integration/test_mini_app_runtime.py tests/integration/test_support_runtime.py -q -p no:cacheprovider` completed green after moving support insight view labels and source-key selection into `app.services.web_admin_dashboard_support_insight_views` with compatibility imports from `app.services.web_admin_dashboard_support_sections`.
- Wave 3 Mini App support escalation insight serializer extraction checkpoint passed after moving escalation lane/action, priority focus, escalation watchlist/trend and operator action trend serializers/summaries into `app.services.web_admin_dashboard_support_escalation_insight_serializers` with compatibility imports from `app.services.web_admin_dashboard_support_insight_serializers`.
- Wave 3 Mini App support triage apply-summary serializer extraction checkpoint passed after moving triage apply history/cross-cut/focus/effectiveness summary payload construction into `app.services.web_admin_dashboard_support_triage_apply_summary_serializers` with compatibility imports from `app.services.web_admin_dashboard_support_triage_summary_serializers`.
- Wave 3 Mini App support ticket list serializer extraction checkpoint passed after moving support list item, close-reason analytics, queue filtering/counting and waiting/stale helpers into `app.services.web_admin_dashboard_support_ticket_list_serializers` with compatibility imports from `app.services.web_admin_dashboard_support_ticket_serializers`.
- Wave 3 Mini App support ticket detail serializer extraction checkpoint passed after moving pinned context, next action, operator hints, profile summary and canned-reply detail payload helpers into `app.services.web_admin_dashboard_support_ticket_detail_serializers` with compatibility imports from `app.services.web_admin_dashboard_support_ticket_serializers`.
- Wave 3 Mini App support insight section extraction checkpoint passed after moving snapshot/live support insights endpoint orchestration, read-model fallback and view slicing into `app.services.web_admin_dashboard_support_insight_sections` with compatibility imports from `app.services.web_admin_dashboard_support_sections`.
- Wave 3 Mini App support ticket section extraction checkpoint passed after moving support ticket detail endpoint SQL loading, profile/payment preview assembly and triage-batch matching into `app.services.web_admin_dashboard_support_ticket_sections` with compatibility imports from `app.services.web_admin_dashboard_support_sections`.
- Wave 3 Mini App support inbox section extraction checkpoint passed after moving support inbox list/search/filter pagination and compact support overview payloads into `app.services.web_admin_dashboard_support_inbox_sections` with compatibility imports from `app.services.web_admin_dashboard_support_sections`.
- Wave 3 analytics model extraction checkpoint passed: targeted analytics ruff, `python -m compileall -q app` and `pytest tests/unit/test_analytics_service.py tests/integration/test_admin_stage7_users_analytics.py tests/integration/test_mini_app_runtime.py -q -p no:cacheprovider` completed green after moving analytics DTO/dataclass contracts into `app.services.analytics_models`.
- Wave 3 analytics lifecycle extraction checkpoint passed: targeted analytics ruff, `python -m compileall -q app`, `python -m app.tools.scan_texts` and `pytest tests/unit/test_analytics_service.py tests/integration/test_admin_stage7_users_analytics.py tests/integration/test_mini_app_runtime.py -q -p no:cacheprovider` completed green after moving lifecycle/source-campaign helper logic into `app.services.analytics_lifecycle`.
- Wave 3 analytics common-helper extraction checkpoint passed: targeted analytics ruff, `python -m app.tools.scan_texts` and `pytest tests/unit/test_analytics_service.py tests/unit/test_service_module_contracts.py tests/integration/test_admin_stage7_users_analytics.py tests/integration/test_mini_app_runtime.py -q -p no:cacheprovider` completed green after moving shared payload/query helpers into `app.services.analytics_common`.
- Wave 3 analytics funnel extraction checkpoint passed: targeted analytics ruff and `pytest tests/unit/test_analytics_service.py tests/unit/test_service_module_contracts.py tests/integration/test_admin_stage7_users_analytics.py tests/integration/test_mini_app_runtime.py -q -p no:cacheprovider` completed green after moving product/source funnel builders into `app.services.analytics_funnel`.
- Wave 3 analytics pricing extraction checkpoint passed: targeted analytics ruff, `python -m compileall -q app`, `python -m app.tools.scan_texts` and `pytest tests/unit/test_analytics_service.py tests/unit/test_service_module_contracts.py tests/integration/test_admin_stage7_users_analytics.py tests/integration/test_mini_app_runtime.py -q -p no:cacheprovider` completed green after moving pricing/offer/product-pair intelligence into `app.services.analytics_pricing`.
- Wave 3 analytics promo/referral extraction checkpoint passed: targeted analytics ruff, `python -m compileall -q app`, `python -m app.tools.scan_texts` and `pytest tests/unit/test_analytics_service.py tests/unit/test_service_module_contracts.py tests/integration/test_admin_stage7_users_analytics.py tests/integration/test_mini_app_runtime.py -q -p no:cacheprovider` completed green after moving promo discount attribution and referral revenue attribution into `app.services.analytics_promo_referral`.
- Wave 3 analytics acquisition extraction checkpoint passed: targeted analytics ruff, `python -m compileall -q app`, `python -m app.tools.scan_texts` and `pytest tests/unit/test_analytics_service.py tests/unit/test_service_module_contracts.py tests/integration/test_admin_stage7_users_analytics.py tests/integration/test_mini_app_runtime.py -q -p no:cacheprovider` completed green after moving source acquisition and acquisition-lifecycle ROI into `app.services.analytics_acquisition`.
- Wave 3 analytics lifecycle-builder extraction checkpoint passed: targeted analytics ruff, `python -m compileall -q app`, `python -m app.tools.scan_texts` and `pytest tests/unit/test_analytics_service.py tests/unit/test_service_module_contracts.py tests/integration/test_admin_stage7_users_analytics.py tests/integration/test_mini_app_runtime.py -q -p no:cacheprovider` completed green after moving lifecycle queue, offer-mix and managed-campaign attribution builders into `app.services.analytics_lifecycle_builders`.
- Wave 3 Mini App admin summary extraction checkpoint passed: admin summary serializer and live read-model builder moved from user-facing `app.services.web_cabinet` into `app.services.web_admin_dashboard_summary_sections`; `web_cabinet` now stays user-facing and `tests/unit/test_service_module_contracts.py` guards that split.
- Wave 3 Mini App read-model action extraction checkpoint passed: targeted read-model ruff, `python -m compileall -q app` and `pytest tests/unit/test_service_module_contracts.py tests/unit/test_admin_read_model_text.py tests/unit/test_admin_read_model_reporting.py tests/integration/test_mini_app_runtime.py -q -p no:cacheprovider` completed green after moving watchlist/action/focus helpers into `app.services.web_admin_dashboard_read_model_actions` with compatibility imports from `app.services.web_admin_dashboard_read_model_sections`.
- Wave 3 Mini App read-model descriptor extraction checkpoint passed: targeted read-model ruff, `python -m compileall -q app` and `pytest tests/unit/test_service_module_contracts.py tests/unit/test_admin_read_model_text.py tests/unit/test_admin_read_model_reporting.py tests/integration/test_mini_app_runtime.py -q -p no:cacheprovider` completed green after moving the tracked analytics/lifecycle/support snapshot descriptor registry into `app.services.web_admin_dashboard_read_model_descriptors` with compatibility imports from `app.services.web_admin_dashboard_read_model_sections`.
- Wave 3 Mini App read-model serializer extraction checkpoint passed: targeted read-model ruff, `python -m compileall -q app` and `pytest tests/unit/test_service_module_contracts.py tests/unit/test_admin_read_model_text.py tests/unit/test_admin_read_model_reporting.py tests/integration/test_mini_app_runtime.py -q -p no:cacheprovider` completed green after moving overview item, drift item, status and view serializers into `app.services.web_admin_dashboard_read_model_serializers` with compatibility imports from `app.services.web_admin_dashboard_read_model_sections`.
- Wave 3 Mini App read-model store extraction checkpoint passed: targeted read-model ruff, `python -m compileall -q app` and `pytest tests/unit/test_service_module_contracts.py tests/unit/test_admin_read_model_text.py tests/unit/test_admin_read_model_reporting.py tests/integration/test_mini_app_runtime.py -q -p no:cacheprovider` completed green after moving snapshot row lookup helpers into `app.services.web_admin_dashboard_read_model_store` with compatibility imports from `app.services.web_admin_dashboard_read_model_sections`.
- Wave 3 Mini App read-model live-builder extraction checkpoint passed: targeted read-model ruff, `python -m compileall -q app` and `pytest tests/unit/test_service_module_contracts.py tests/unit/test_admin_read_model_text.py tests/unit/test_admin_read_model_reporting.py tests/integration/test_mini_app_runtime.py -q -p no:cacheprovider` completed green after moving live overview/watchlist/actions/drift recompute builders into `app.services.web_admin_dashboard_read_model_live` with compatibility imports from `app.services.web_admin_dashboard_read_model_sections`.
- Wave 3 Mini App read-model core extraction checkpoint passed after moving read-model view/status constants, payload decode, coercion, staleness, status note and severity helpers into `app.services.web_admin_dashboard_read_model_core` with compatibility imports from `app.services.web_admin_dashboard_read_model_serializers`.
- Wave 3 Mini App read-model drift serializer extraction checkpoint passed after moving drift item and drift tone serialization into `app.services.web_admin_dashboard_read_model_drift_serializers` with compatibility imports from `app.services.web_admin_dashboard_read_model_serializers`.
- Wave 3 Mini App read-model watchlist helper extraction checkpoint passed after moving snapshot/live watchlist item builders, watchlist sort and drift leader helpers into `app.services.web_admin_dashboard_read_model_watchlist` with compatibility imports from `app.services.web_admin_dashboard_read_model_actions`.
- Wave 3 Mini App read-model action digest helper extraction checkpoint passed after moving action recommendation, category label and grouped action digest item builders into `app.services.web_admin_dashboard_read_model_action_digest` with compatibility imports from `app.services.web_admin_dashboard_read_model_actions`.
- Wave 3 Mini App read-model live descriptor extraction checkpoint passed after moving live descriptor dispatch and admin analytics text live payload builders into `app.services.web_admin_dashboard_read_model_live_descriptors` with compatibility imports from `app.services.web_admin_dashboard_read_model_live`.
- Wave 3 Mini App read-model live overview extraction checkpoint passed after moving the live read-model diagnostics overview builder into `app.services.web_admin_dashboard_read_model_live_overview` with compatibility imports from `app.services.web_admin_dashboard_read_model_live`.
- Wave 3 Mini App lifecycle extraction checkpoint passed: targeted lifecycle ruff, `python -m compileall -q app` and `pytest tests/unit/test_service_module_contracts.py tests/integration/test_mini_app_runtime.py tests/integration/test_admin_stage7_users_analytics.py -q -p no:cacheprovider` completed green after moving lifecycle live payload construction into `app.services.web_admin_dashboard_lifecycle_live` and compact lifecycle summary serializers into `app.services.web_admin_dashboard_lifecycle_serializers`.
- Wave 3 Mini App lifecycle source serializer extraction checkpoint passed after moving source acquisition, source campaign, source ROI, source opportunities, source actions, source highlights and source watchlist view serialization into `app.services.web_admin_dashboard_lifecycle_source_serializers` with compatibility imports from `app.services.web_admin_dashboard_lifecycle_live`.
- Wave 3 Mini App lifecycle attribution serializer extraction checkpoint passed after moving rule, ROI, highlight, wave, family and variant lifecycle view serialization into `app.services.web_admin_dashboard_lifecycle_attribution_serializers` with compatibility imports from `app.services.web_admin_dashboard_lifecycle_live`.
- Wave 3 Mini App lifecycle campaign source summary serializer extraction checkpoint passed after moving source campaign, source ROI, source opportunity, source action, source highlight and source watchlist summary serialization into `app.services.web_admin_dashboard_lifecycle_campaign_source_serializers` with compatibility imports from `app.services.web_admin_dashboard_lifecycle_serializers`.
- Wave 3 Mini App analytics serializer extraction checkpoint passed: targeted analytics ruff, `python -m compileall -q app` and `pytest tests/unit/test_service_module_contracts.py tests/unit/test_analytics_service.py tests/integration/test_mini_app_runtime.py tests/integration/test_admin_stage7_users_analytics.py -q -p no:cacheprovider` completed green after moving shared pricing/acquisition/conversion/promo/referral serializers into `app.services.web_admin_dashboard_analytics_serializers`.
- Wave 3 read-model reporting DTO extraction checkpoint passed: targeted reporting ruff, `python -m compileall -q app` and `pytest tests/unit/test_service_module_contracts.py tests/unit/test_admin_read_model_reporting.py tests/unit/test_admin_home.py tests/unit/test_health_service.py tests/unit/test_observability.py tests/unit/test_report_service.py -q -p no:cacheprovider` completed green after moving read-model reporting dataclass contracts into `app.services.admin_read_model_reporting_models` with compatibility re-exports from `app.services.admin_read_model_reporting`.
- Wave 3 read-model reporting summary extraction checkpoint passed: targeted reporting ruff, `python -m compileall -q app` and `pytest tests/unit/test_service_module_contracts.py tests/unit/test_admin_read_model_reporting.py tests/unit/test_admin_home.py tests/unit/test_health_service.py tests/unit/test_observability.py tests/unit/test_report_service.py -q -p no:cacheprovider` completed green after moving snapshot payload-to-summary builders into `app.services.admin_read_model_reporting_summaries` with compatibility re-exports from `app.services.admin_read_model_reporting`.
- Wave 3 read-model reporting digest extraction checkpoint passed: targeted reporting ruff, `python -m compileall -q app` and `pytest tests/unit/test_service_module_contracts.py tests/unit/test_admin_read_model_reporting.py tests/unit/test_admin_home.py tests/unit/test_health_service.py tests/unit/test_observability.py tests/unit/test_report_service.py -q -p no:cacheprovider` completed green after moving digest, focus and compact payload renderers into `app.services.admin_read_model_reporting_digests` with compatibility re-exports from `app.services.admin_read_model_reporting`.
- Wave 3 read-model reporting loader extraction checkpoint passed: targeted reporting ruff, `python -m compileall -q app` and `pytest tests/unit/test_service_module_contracts.py tests/unit/test_admin_read_model_reporting.py tests/unit/test_admin_home.py tests/unit/test_health_service.py tests/unit/test_observability.py tests/unit/test_report_service.py -q -p no:cacheprovider` completed green after moving async snapshot/live loader functions into `app.services.admin_read_model_reporting_loaders`; `app.services.admin_read_model_reporting` now stays a compatibility facade.
- CI and `scripts/deploy.sh` now call `python -m app.tools.quality_gate --summary-json ...`, so local, CI and server-side gates share the same scoped check sequence, including deploy-safe tracked-file repository sanity, and can persist machine-readable step timing/status. CI uploads `.tmp/quality-gate.json` as the `quality-gate-summary` artifact. Webhook deploy smoke can also persist `smoke-$DEPLOY_STAMP.json` with checked surfaces and latency baseline.

P1 fixed during this checkpoint:

- `scan_texts` found mojibake in operator-facing literals in `app.services.admin_home`, `app.services.observability`, `app.services.report_service` and one Mini App integration fixture.
- Fixed only damaged UI/test literals; no commercial payloads, callback payloads, slash commands, payment payloads or invite/access contracts were changed.

Residual risks to keep visible:

- The worktree is intentionally dirty from the ongoing roadmap implementation. Do not deploy or push without reviewing and staging the intended scope only.
- Root-level `compileall .` remains unsuitable while `.vendor`, `.tooling`, `.tmp` and caches live under the repo root; use `python -m app.tools.quality_gate` or scoped compile for `app tests alembic scripts`.
- `data/db.json` is explicitly ignored and `python -m app.tools.repo_sanity` asserts it must not exist in tracked files.
- `app.services.analytics` is now a thin snapshot orchestrator with compatibility re-exports; the remaining analytics modularization risk is mostly payload contract drift between the split modules and admin serializers. `app.services.support` is now a thin compatibility/orchestration facade over `support_models`, `support_catalog`, `support_reply_packs`, `support_sla`, `support_open_queues`, `support_triage_apply`, `support_ticket_flow` and `support_insight_trends`; remaining support risk is contract drift between those split modules and Mini App/admin serializers. Mini App admin summary code now lives in `web_admin_dashboard_summary_sections`; support triage mutations now live in `web_admin_dashboard_support_actions`; support insights now live in `web_admin_dashboard_support_insight_serializers`; support ticket/list/queue serializers now live in `web_admin_dashboard_support_ticket_serializers`; `web_cabinet` should not regain admin analytics imports.
- Deploy rollback backups now use `BACKUP_ARCHIVE_NAME=predeploy-$DEPLOY_STAMP-db-backup.tar.gz`; ordinary manual backups still keep the timestamped archive format.

## Admin commands

## Observability 2.0

- Runtime stores the last 20 critical errors in memory with sanitized messages.
- Worker status is tracked for `subscription_expirer`, `broadcast_sender`, `backup_worker`, `crypto_reconciler`, `channel_guard`, `admin_reports` and `retention_automation`.
- Structured logs redact token-like values, invite links and secret assignments.
- `CRITICAL_ERROR_WEBHOOK_URL` is optional and disabled by default.

## Role-based admin permissions

- `owner` - full access, including `/admin_roles` and `Р В РЎСљР В Р’В°Р РЋР С“Р РЋРІР‚С™Р РЋР вЂљР В РЎвЂўР В РІвЂћвЂ“Р В РЎвЂќР В РЎвЂ`.
- `admin` - operational access without role management/settings.
- `support` - support inbox, audit, diagnostics and read-only user directory.
- `analyst` - analytics, audit and diagnostics.

Guardrails now enforced in runtime:

- manual subscription grants, direct messages and user blocking are owner/admin only;
- broadcasts and finance/payment recovery are owner/admin only;
- support ticket inbox is support/admin/owner;
- settings and role changes are owner only.

- `/admin` - open the admin panel.
- `/admin_channel_check` - live-check connected channels and the bot's rights.
- `/admin_health` - runtime health dashboard for admins, including read-model snapshot health and a short live drift summary.
- `/admin_finance` - read-only finance dashboard with Stars/Crypto summary and CSV export.
- `/admin_audit` - audit viewer with filters by target user, actor, action and period plus redacted CSV export.
- `/admin_roles` - owner-only role management for `owner`, `admin`, `support` and `analyst`.
- `/admin_observability` - recent critical errors, worker status, Telegram API errors, backup result, read-model snapshot summary, watchlist/action digest and live drift compare with query/payload/build regression leaders.
  The in-bot screen also exposes `Read-models`, `Watchlist`, `Live overview` and `Snapshot vs live` callbacks for operator-side drill-down without opening Mini App admin.
- `/admin` also surfaces the current top read-model action and, when live compare regresses, the current top read-model drift.
- Bot-side operator surfaces now reuse the same compact read-model action/drift digest helpers, so `/admin`, `/admin_health`, `/admin_observability` and scheduled reports describe the same top regression/watch item.
- `/admin_observability` and scheduled admin reports now also include a compact read-model watchlist summary, so the top snapshot-side missing/stale/budget issue is visible even without opening the full watchlist view.
- `/admin` now shows a single compact `Read-model summary` line for the same watch/action/drift layer, and `/admin_health` includes a separate compact `Read-model watchlist` metric for the snapshot-side queue.
- Scheduled reports now also include a compact `Read-model summary` line, which prefers live drift regressions over snapshot watchlist issues and falls back to the next action digest when no stronger signal exists.
- `/admin_observability` now renders the same `Read-model focus` and compact `summary` line inside the detailed diagnostics screen, and the Mini App `Read-model diagnostics` card shows the same pair for each overview/watchlist/actions/drift view.
- `/admin_crypto_invoices` - Crypto Pay reconciliation summary and latest invoice statuses.
- `/admin_crypto_diag <user_id|invoice_id>` - detailed Crypto Pay diagnostics for a user or a specific invoice.
- `/admin_promo_create CODE TYPE VALUE LIMIT [TARIFF_ID|-] [VALID_DAYS|-] [from=ISO] [until=ISO] [first=0|1] [per_user=N] [campaign=NAME] [notes=TEXT]` - create a promo code.
- `/admin_promo_disable CODE` - disable a promo code.
- `/admin_promo_view CODE` - show the promo card with scope, validity and abuse rules.
- `/admin_promo_list [QUERY]` - search promo codes by code or campaign.
- `/admin_promo_stats CODE` - show promo statistics.
- `/admin_referrals` - referral analytics with top referrers, suspicious cases and referral revenue context.
- `/admin_support` - support inbox with open/closed ticket views and reply actions.
- `/promo CODE` - apply a user promo code.
- `/my_referrals` - user referral dashboard with link, counts and pending reward days.
- `/paysupport` - user payment support text.
- `/terms` - show the managed terms text.
- `/privacy` - show the managed privacy text.
- `/refunds` - show the managed refund policy text.
- `/support` - open the in-bot support screen and create a ticket.
- `/cabinet` - send a Telegram WebApp button for the Mini App cabinet.

## Channel diagnostics

`/admin_channel_check` verifies:

- that `getMe` succeeds;
- that the channel is reachable through Telegram API;
- that the bot is present in the channel;
- that the bot is an administrator;
- that the bot can create invite links;
- that the bot can restrict or ban users;
- that stored rights in the database do not diverge from live Telegram state.

If the report shows a `store/live` mismatch, open `Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦` and refresh the channel.

## Webhook runtime

When `USE_WEBHOOK=true`, the process exposes:

- `POST WEBHOOK_PATH` for Telegram updates;
- `GET /healthz` for liveness;
- `GET /readyz` for readiness.

Readiness fails with HTTP `503` if the database is unavailable or the backup directory cannot be prepared.

Common webhook failures:

- `Missing required environment variables ... PUBLIC_WEBHOOK_URL`:
  set `PUBLIC_WEBHOOK_URL` when `USE_WEBHOOK=true`.
- `Missing required environment variables ... WEBHOOK_SECRET_TOKEN`:
  set `WEBHOOK_SECRET_TOKEN` when `USE_WEBHOOK=true`.
- Telegram receives `401 Unauthorized` on webhook delivery:
  check that the reverse proxy keeps the `X-Telegram-Bot-Api-Secret-Token` header intact and that `.env` uses the same secret as Telegram.
- Telegram does not deliver updates after deploy:
  check the public path, reverse proxy and the configured webhook URL in logs.
- `GET /readyz` returns `503`:
  verify database connectivity and permissions to `BACKUP_DIRECTORY`.

## Smart onboarding

New users now see a three-step onboarding flow on the first `/start`.

It explains:

- what the bot does;
- how payment works;
- how to get into the private channel after payment.

Operational rules:

- existing users are backfilled as completed during migration and must not see onboarding again;
- `Пропустить` marks onboarding completed immediately;
- partial progress is stored in `users.onboarding_step`;
- if the user already paid or already has a subscription, onboarding auto-completes and the normal home screen opens.

If someone reports that `/start` keeps showing onboarding unexpectedly:

- verify whether `users.onboarding_completed_at` is empty for that user;
- verify that the user really has no successful payments and no subscriptions yet;
- if needed, complete onboarding manually by setting `onboarding_completed_at` in the database.
## Expiration warnings and grace period

The expiration worker runs in four steps:

- warning 3 days before expiry, if `WARNING_3D_ENABLED=true`;
- warning 1 day before expiry, if `WARNING_1D_ENABLED=true`;
- expired notice immediately after the subscription ends;
- revoke only after `GRACE_PERIOD_HOURS`.

If the user renews before revoke, access is extended normally and the old grace-period record must not be revoked again.

## Admin reports

Background scheduler sends admin summaries at `09:00` in `TIMEZONE`.

Rules:

- daily report is sent once per local day;
- weekly report is additionally sent on Monday and deduplicated by ISO week;
- scheduled reports now include a read-model drift digest, so budget/query/payload regressions are visible even outside Mini App admin.
- delivery goes only to `ADMIN_IDS`;
- duplicate protection is stored in `audit_logs` with actions `admin_report_sent_daily` and `admin_report_sent_weekly`.

Report payload includes:

- new users;
- paid payments count;
- Stars revenue;
- Crypto revenue by asset;
- active subscriptions;
- subscriptions expired during the period;
- anomalies from recent runtime critical errors.

If reports do not arrive:

- check `/admin_observability` and worker status `admin_reports`;
- verify `ADMIN_IDS` is not empty;
- verify `TIMEZONE` is set correctly;
- inspect audit events `admin_report_sent_daily` and `admin_report_sent_weekly`;
- verify the process was alive around `09:00` local time.

## Retention automation

Lifecycle retention runs in the background scheduler and covers:

- `first_payment_follow_up` - first successful payment in the last 24h;
- `never_joined_after_payment` - payment is active but the user still has not joined;
- `expired_recently` - paid access expired recently and can be won back;
- `inactive_paid` - previously paid user stayed inactive long enough for a reactivation touch;
- `lost_after_trial` - trial user expired and should get the trial-specific upgrade message.

Guardrails:

- every segment is deduplicated through `audit_logs`;
- blocked/admin users are skipped;
- trial-loss messaging is exclusive and must not degrade into the generic recent-expiry flow in the same window.

If retention messages stop arriving:

- check `/admin_observability` and worker status `retention_automation`;
- inspect recent audit actions `retention_*_sent`;
- inspect audit payload fields `campaign_rule_key`, `campaign_family`, `campaign_variant`, `offer_strategy` and `primary_offer_source` to see which lifecycle wave selected the offer mix;
- use Mini App admin `CRM lifecycle -> ROI` to compare `sent -> paid -> invite -> second product revenue` by managed rule before changing lifecycle copy;
- use `Promo / Referral` in admin analytics or Mini App summary to compare promo discount pressure against referred-user revenue before tuning acquisition campaigns;
- use `Acquisition ROI` in admin analytics or Mini App summary to compare first-touch sources by `acquired -> paid -> repeat -> lifetime revenue`, then check lifecycle 30d revenue, second-product attach and top rule/wave before reworking onboarding or deep-link traffic;
- verify `BOT_PUBLIC_USERNAME`/deep links if CTA links look wrong.

## Runtime health dashboard

`/admin_health` shows:

- process uptime;
- bot username and `getMe` availability;
- whether active channels exist in the database;
- store read/write status;
- total users;
- active subscriptions;
- payments for the current day;
- last update id and event type, when telemetry exists;
- last maintenance run from the background scheduler;
- last Telegram API error, if recorded;
- timestamp of the latest backup.
- read-model snapshot health, including missing/stale/budget alerts.

`/admin_observability` additionally shows:

- read-model snapshot summary from stored admin read models;
- explicit live `snapshot vs live` drift compare for the heaviest admin surfaces.
- an operator watchlist that ranks the top missing/stale/budget/drift issues.
- an operator action digest that turns the top read-model issues into concrete next-step recommendations.

If `Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦: Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦` is `?`, do not restart blindly. Check the database and DB user permissions first.

If `Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦ Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦` is `?`, verify `BOT_TOKEN`, network connectivity and Telegram API reachability.

## Finance dashboard

`/admin_finance` and `menu:admin:payments` show read-only Stars/Crypto totals, unpaid and expired crypto invoice counts, promo/referral counters and top tariffs.

Use the CSV export buttons to download day/week/month/all reports without raw payloads, invite links or secrets.

## Crypto Pay diagnostics

Use `/admin_crypto_invoices` to inspect active, paid-but-not-activated and expired invoices.
Use `/admin_crypto_diag <user_id|invoice_id>` to inspect one invoice or a specific user history.

If `Paid but not activated` is not zero:

- inspect the target invoice with `/admin_crypto_diag`;
- check audit events `crypto_invoice_paid`, `crypto_subscription_activated`, `crypto_invoice_duplicate`, `crypto_reconcile_error`;
- verify the linked tariff/channel still exists;
- verify the reconcile summary has a recent successful run.

## Broadcast diagnostics

The broadcast screen now supports:

- segmentation by `all`, `active`, `expired`, `never_paid`, `expires_soon`, `pending_join`, specific tariff and specific channel;
- preview with recipient count and the first sample recipients;
- explicit confirm before queueing;
- reusable templates;
- delivery report with sent, failed, blocked and `rate_limited` counts.

If a broadcast behaves unexpectedly:

- open the broadcast card and check `Р В РЎвЂєР РЋР С“Р РЋРІР‚С™Р В Р’В°Р В Р’В»Р В РЎвЂўР РЋР С“Р РЋР Р‰`, `Р В РЎвЂєР РЋРІвЂљВ¬Р В РЎвЂР В Р’В±Р В РЎвЂўР В РЎвЂќ`, `Rate limited` and `Р В РІР‚вЂќР В Р’В°Р В Р’В±Р В Р’В»Р В РЎвЂўР В РЎвЂќР В РЎвЂР РЋР вЂљР В РЎвЂўР В Р вЂ Р В Р’В°Р В Р’В»Р В РЎвЂ Р В Р’В±Р В РЎвЂўР РЋРІР‚С™Р В Р’В°`;
- inspect recent `broadcast_batch_processed` audit events;
- verify the selected segment really contains users now, not historically;
- for `pending_join`, verify the user still has an active invite link;
- for `expires_soon`, verify the subscription expires within the next 3 days.

A plain admin message without the broadcast FSM context must not queue a campaign.

## Legal texts

`/terms`, `/privacy`, `/refunds` and the help-screen legal buttons are backed by managed text templates.
`/paysupport` now renders the managed `payment_support` text.

If the wording must be changed:

- open `/admin` -> `?? ??????`;
- edit `terms`, `privacy`, `refund_policy` or `payment_support`;
- reset the template to default if the customized version became broken.

## Support ticket diagnostics

The support flow now stores `support_tickets` and `support_messages` in the database.

If a user says support is not responding:

- verify `/support` opens the support screen and allows category selection;
- verify the user does not already have an open ticket blocking new creation;
- verify the user did not hit the daily creation cap of 3 tickets per 24 hours;
- open `/admin_support` and check whether the ticket is in the `open` inbox;
- open the ticket and verify reply/close/reopen actions work;
- check recent `support_ticket_*` audit events for create, reply, close and reopen actions.

## Audit viewer

`/admin_audit` and `menu:admin:audit` show recent audit events with filters by target user, actor, action and period.

Use the prompt buttons to set user filters by internal ID (`id:123`) or Telegram ID (`tg:755815181`).

CSV export always uses redacted payloads: direct message text, invite links, token-like values and other sensitive raw fields are hidden before delivery.

If you need to investigate a manual grant, recovery or suspicious payment flow:

- open `/admin_audit`;
- narrow the period first, then add target user or actor filters;
- inspect the detail card for the exact event;
- jump into the linked user profile when the event has a target or actor user;
- export CSV if you need an external incident timeline without exposing secrets.


## Promo diagnostics

If a user says the discount was not applied:

- check `/admin_promo_stats CODE`;
- verify the promo is active, already started and not expired;
- verify the tariff matches `TARIFF_ID` when the promo is scoped;
- verify irst_purchase_only and per_user_limit conditions on the promo card;
- verify the user is paying through Telegram Stars, not Crypto Pay;
- inspect audit events `promo_applied_pending`, `promo_applied_free_days` and `payment_paid_stars`.

## Referral diagnostics

Use `/my_referrals` to verify that the user sees:

- the deep link with `ref_*` payload;
- invited users count;
- paid referrals count;
- earned reward days;
- pending reward days for the next renewal.

Use `/admin_referrals` to verify that admins see:

- total invited users;
- total paid referrals;
- conversion percent;
- rewards issued and reward days;
- top referrers;
- suspicious cases from audit events.

Suspicious reasons currently include `already_bound`, `already_customer`, `self_referral` and duplicate reward attempts.

If referral numbers look wrong:

- inspect audit events `referral_bound`, `referral_reward_granted`, `referral_reward_applied`, `referral_suspicious`;
- verify the referred user paid through the normal successful payment flow;
- verify the reward was not already granted earlier for that referred user.
## Local checks

```bash
python -m compileall app tests alembic
ruff check .
pytest -q
python -m app.healthcheck
```

## Server checks

```bash
docker compose ps
docker compose logs --tail=100 bot
python -m app.healthcheck
```

For webhook deployments, also verify:

```bash
curl -fsS http://127.0.0.1:8080/healthz
curl -fsS http://127.0.0.1:8080/readyz
```

## Common failures

- `Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦ Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦ Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦` or `bot Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦ Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦ Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦`:
  check `chat_id`, ensure the bot is in the channel and has not been removed.
- `Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦ Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦: Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦`:
  grant administrator rights.
- `Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦ Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦ invite links: Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦`:
  enable invite permissions.
- `Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦ Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦ Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦: Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦`:
  enable restrict/ban permissions.
- `getMe` does not pass:
  verify `BOT_TOKEN`, network and Telegram API reachability.
- `Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦: Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦` does not pass:
  verify DB user permissions, read-only mode and transaction health.
- `Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦ backup: Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦ Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦ Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦`:
  verify `BACKUP_*` settings and trigger a manual backup from the admin panel.
- `Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦ Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦ Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦Р В РЎвЂ”Р РЋРІР‚вЂќР В РІР‚В¦`:
  verify promo scope, promo status and that payment was done through Stars.

## Repo hygiene

If local junk appears in the repository or you suspect a secret leak:

- check `.gitignore` and `tests/unit/test_repo_hygiene.py`;
- verify `.env`, `dev.db`, `.venv/`, `.pytest_cache/`, `.ruff_cache/`, `.tmp/`, `.vendor/`, `.tooling/` and runtime logs are not tracked;
- verify tracked source/docs do not contain Telegram token-like strings.







## Mini App cabinet

When `USE_WEBHOOK=true`, the same aiohttp runtime serves the cabinet page at `MINI_APP_PATH`.
All cabinet API calls require a valid Telegram `initData` signature and reject expired auth data with `401 unauthorized`.

Endpoints:

- `GET MINI_APP_PATH` - HTML shell for Telegram WebApp.
- `POST MINI_APP_PATH/api/auth` - validate `initData` once and sync the Telegram user into the database.
- `GET MINI_APP_PATH/api/bootstrap` - own profile, grouped products, active product access, flat tariffs, payments, referral stats, pending promos, support state and action links.
- `GET MINI_APP_PATH/api/users/{telegram_id}/profile` - own profile, or another profile for admins only.
- `GET MINI_APP_PATH/api/admin/summary` - admin-only analytics snapshot.
- `GET MINI_APP_PATH/api/admin/dashboard` - Mini App admin dashboard with overview cards and capability-aware sections.
- `GET MINI_APP_PATH/api/admin/dashboard?sections=summary,...` - section-scoped admin dashboard payload for lazy Mini App loading and lighter read paths.
- `GET MINI_APP_PATH/api/admin/conversion` - admin-only conversion/product console payload with global funnel counters, catalog inventory topline and product-level funnel detail, snapshot-first by default.
- `GET MINI_APP_PATH/api/admin/acquisition` - admin-only acquisition/source console payload with source funnel and cohort topline, snapshot-first by default.
- `GET MINI_APP_PATH/api/admin/promo-referrals` - admin-only promo/referral console payload with promo campaign detail and referral leader detail, snapshot-first by default.
- `GET MINI_APP_PATH/api/admin/pricing` - admin-only pricing and offer console payload with offer leaders, product-pair leaders and cross-sell wave leaders.
- `GET MINI_APP_PATH/api/admin/read-models?view=overview|watchlist|actions|drift&limit=N&source=snapshot|live` - admin-only read-model diagnostics payload. `overview` reports snapshot freshness, query budgets, payload size and the heaviest/stalest admin surfaces; `watchlist` ranks open missing/stale/budget/drift issues; `actions` groups those issues into recommended next steps; `drift` performs an explicit `snapshot vs live` compare and ranks query/payload/build regressions. All views may also include `focus_summary` plus `operator_digest_summary` with the current compact operator-facing signal and short watch/action/drift digest.
- `GET MINI_APP_PATH/api/admin/users?filter=...&query=...&page=...` - admin-only filterable user directory payload.
- `GET MINI_APP_PATH/api/admin/payments?provider=...&query=...&page=...` - admin-only filterable payments payload with redacted fields only.
- `GET MINI_APP_PATH/api/admin/support?status=...&queue=...&query=...&page=...` - admin-only support inbox payload with open/closed filters, queue triage (`all`, `awaiting_admin`, `awaiting_user`, `stale`), wait-state counters, primary action-lane labels, escalation-lane labels, read-only support insights, SLA hotspots, canned-reply outcomes and ticket previews.
- `GET MINI_APP_PATH/api/admin/support/{ticket_id}` - admin-only ticket thread with explicit `next_action`, batch-aware `triage_batch`, triage pack/route hints, pinned operator context, escalation hints, profile/subscription summary, recent payments, suggested canned replies, close-reason analytics and operator-safe support metadata for fast triage.
- `GET MINI_APP_PATH/api/admin/support/insights?view=hotspots|sla_queue|sla_actions|pack_outcomes|close_trends|action_lanes|next_actions|action_routes|triage_queue|triage_plans|triage_confirm|triage_apply_history|triage_apply_routes|triage_apply_actors|triage_apply_replies|triage_apply_actor_replies|triage_apply_route_actors|triage_apply_reply_packs|triage_apply_route_reply_actors|triage_apply_focus|triage_apply_effectiveness|escalation_lanes|escalation_actions|priority_focus|escalation_watchlist|escalation_trends|operator_action_trends&limit=N` - admin-only support insights console payload for SLA hotspots, SLA queue, next-action queue, action routes, pack-aware triage queues, `triage_plans` with route-aware canned reply previews, `triage_confirm` with preview-only bulk triage confirmation notes, `triage_apply_history` with recent batch apply actions, `triage_apply_routes` with aggregated route/pack/reply apply history, `triage_apply_actors` with aggregated actor effectiveness by top route/reply, `triage_apply_replies` with aggregated reply mix by top actor/route, `triage_apply_actor_replies` with aggregated actor/reply usage by top route/pack, `triage_apply_route_actors` with aggregated route/actor usage by top reply/pack, `triage_apply_reply_packs` with aggregated reply/pack usage by top route/actor, `triage_apply_route_reply_actors` with aggregated route/reply/actor usage by top pack, `triage_apply_focus` with a compact ranked digest over those cross-cuts, `triage_apply_effectiveness` with the strongest recent apply path by route/reply/actor/pack coverage, sample ticket jumps for `sla_queue` / `next_actions` / `action_routes` / `triage_queue` / `triage_plans` / `triage_confirm` / `triage_apply_history` / `triage_apply_routes` / `triage_apply_actors` / `triage_apply_replies` / `triage_apply_actor_replies` / `triage_apply_route_actors` / `triage_apply_reply_packs` / `triage_apply_route_reply_actors`, canned-reply outcomes, close-reason trend slices, managed action lanes, managed escalation lanes, escalation-action mix, SLA action plans, priority handling, escalation watchlist, escalation trends and operator action trends.
- `POST MINI_APP_PATH/api/admin/actions/support-triage-confirm` - admin-only operator-safe triage confirm preview. Accepts `triage_key` and optional `ticket_id`, writes audit `webapp_admin_support_triage_confirm_preview`, and returns a preview-only manual draft with primary canned reply, sample tickets, signed confirm token and explicit operator steps. No bulk reply is sent automatically.
- `POST MINI_APP_PATH/api/admin/actions/support-triage-apply` - admin-only limited triage apply flow. Accepts `triage_key`, `confirm_token`, optional `reply_key` and optional `ticket_id`, writes audit `webapp_admin_support_triage_apply`, revalidates the live route/pack before sending and applies only canned replies from the confirmed pack.
- The dashboard `support` overview stays compact on purpose; the full support insights payload is lazy-loaded from `/api/admin/support/insights`.
- The dashboard `summary` stays compact too: only top lifecycle/pricing/acquisition/promo/referral/conversion signals are embedded there. Product funnel detail lives in the dedicated conversion console, source/cohort detail lives in the dedicated lazy-loaded acquisition console, promo/referral detail lives in the dedicated promo/referral console, and managed-wave / touch-family / retention detail stays in the lifecycle console.
- The dashboard `summary` and `/api/admin/summary` now also expose compact snapshot-backed `read_model_focus`, `read_model_digest` and `read_model_operator_summary` previews, so operators can see the top read-model issue plus the short watch/action summary before opening the full diagnostics console.
- `GET MINI_APP_PATH/api/admin/lifecycle?view=rules|roi|sources|source_campaigns|source_roi|source_opportunities|source_actions|source_highlights|source_watchlist|highlights|waves|families|variants&limit=N` - admin-only CRM lifecycle dataset for managed waves, ROI, highlights and attribution cuts.
- `POST MINI_APP_PATH/api/admin/actions/channel-check` - admin-only live channel check that also writes audit `webapp_admin_channel_check`.

If the cabinet does not open correctly:

- verify `PUBLIC_WEBHOOK_URL`, `MINI_APP_PATH` and optional `BOT_PUBLIC_USERNAME`;
- verify reverse proxy routing to the aiohttp app port;
- verify Telegram opens the page from a WebApp button and not from a stale browser tab;
- if APIs return `401`, regenerate fresh `initData` by reopening the Mini App from Telegram;
- if APIs return `403`, verify the requested target user and admin role.
- if Mini App admin panels are empty, verify the role has the required permissions (`admin_panel`, `users_view`, `payments`, `support`, `diagnostics`, `analytics`).
- if `Read-model diagnostics` shows `missing` or stale entries, verify the background scheduler is refreshing `admin_read_models` and use `?source=live` to compare against the stored snapshot.
- if `CRM lifecycle -> ROI` is empty, verify there are lifecycle audit events with `campaign_rule_key` and at least one attributed paid conversion in the selected window.
- if the Mini App support inbox opens but thread details fail, verify the role still has `support` permission and the ticket id exists.
- use `bash scripts/smoke_webhook_runtime.sh` after webhook deploys; it auto-loads `.env` from the project root, and with `BOT_TOKEN` plus `ADMIN_IDS` it also exercises authorized Mini App auth plus admin dashboard/read-models/watchlist/actions/drift/lifecycle/users/payments/support/support-insights endpoints.
- the smoke output now prints `Deploy stamp`, `Rollback backup` and a latency baseline for `/healthz`, `/readyz`, Mini App page, webhook and key authorized admin endpoints.
- Mini App admin analytics/support payloads now include `generated_at`, `staleness_seconds`, `build_duration_ms`, `query_count`, `query_budget`, `query_budget_ok`, `payload_bytes`, `payload_budget`, `payload_budget_ok` and `source=snapshot|live`; dashboard reads also support `sections=...` slicing. Use `?source=live` for an admin-only forced recompute when investigating snapshot freshness.
- if user buy/tariffs screens show a product picker unexpectedly, verify more than one active channel currently has at least one active tariff.

## Content / FAQ CMS

- Пользовательские страницы `FAQ`, `Правила канала`, `После оплаты`, `Crypto Pay`, `Оферта` рендерятся через managed `TextTemplate`.
- Раздел `Возвраты` остаётся доступен и через legal-flow, и как часть content-registry.
- Для безопасного рендера content-страницы экранируют HTML/markup из шаблона, поэтому админский текст не ломает caption-разметку.
- Быстрый вход для админа: `/admin_content` или кнопка `📚 Content / FAQ CMS` внутри `✍️ Тексты`.

## Smart channel guard

- Фоновый worker проверяет только активные каналы через live diagnostics.
- Если бот исключён, потерял admin-статус или права `invite/restrict`, владельцы получают alert в Telegram.
- Повторяющиеся alert-сообщения по одной и той же проблеме подавляются до изменения состояния.
- Для ручной расшифровки проблемы используйте `/admin_channel_check`.
