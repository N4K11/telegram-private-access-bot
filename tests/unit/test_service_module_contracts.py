from __future__ import annotations

from app.services import (
    admin_read_model_reporting,
    admin_read_model_reporting_digests,
    admin_read_model_reporting_loaders,
    admin_read_model_reporting_models,
    admin_read_model_reporting_summaries,
    analytics,
    analytics_acquisition,
    analytics_common,
    analytics_funnel,
    analytics_lifecycle,
    analytics_lifecycle_builders,
    analytics_models,
    analytics_pricing,
    analytics_promo_referral,
    support,
    support_action_queues,
    support_catalog,
    support_escalation_queues,
    support_insight_trends,
    support_models,
    support_open_queues,
    support_queue_ranking,
    support_reply_packs,
    support_sla,
    support_sla_queues,
    support_ticket_flow,
    support_triage_apply,
    support_triage_apply_combinations,
    support_triage_apply_core,
    support_triage_apply_history,
    support_triage_apply_notes,
    support_triage_apply_rankings,
    support_triage_apply_replies,
    web_admin_dashboard_analytics_sections,
    web_admin_dashboard_analytics_serializers,
    web_admin_dashboard_lifecycle_attribution_serializers,
    web_admin_dashboard_lifecycle_campaign_source_serializers,
    web_admin_dashboard_lifecycle_live,
    web_admin_dashboard_lifecycle_sections,
    web_admin_dashboard_lifecycle_serializers,
    web_admin_dashboard_lifecycle_source_serializers,
    web_admin_dashboard_read_model_action_digest,
    web_admin_dashboard_read_model_actions,
    web_admin_dashboard_read_model_core,
    web_admin_dashboard_read_model_descriptors,
    web_admin_dashboard_read_model_drift_serializers,
    web_admin_dashboard_read_model_live,
    web_admin_dashboard_read_model_live_descriptors,
    web_admin_dashboard_read_model_live_overview,
    web_admin_dashboard_read_model_sections,
    web_admin_dashboard_read_model_serializers,
    web_admin_dashboard_read_model_store,
    web_admin_dashboard_read_model_watchlist,
    web_admin_dashboard_summary_sections,
    web_admin_dashboard_support_action_insight_serializers,
    web_admin_dashboard_support_actions,
    web_admin_dashboard_support_closed_insight_serializers,
    web_admin_dashboard_support_escalation_insight_serializers,
    web_admin_dashboard_support_inbox_sections,
    web_admin_dashboard_support_insight_sections,
    web_admin_dashboard_support_insight_serializers,
    web_admin_dashboard_support_insight_views,
    web_admin_dashboard_support_sections,
    web_admin_dashboard_support_ticket_detail_serializers,
    web_admin_dashboard_support_ticket_list_serializers,
    web_admin_dashboard_support_ticket_sections,
    web_admin_dashboard_support_ticket_serializers,
    web_admin_dashboard_support_triage_apply_serializers,
    web_admin_dashboard_support_triage_apply_summary_serializers,
    web_admin_dashboard_support_triage_apply_view_serializers,
    web_admin_dashboard_support_triage_queue_serializers,
    web_admin_dashboard_support_triage_summary_serializers,
    web_cabinet,
)


def test_support_module_reexports_modular_contracts() -> None:
    assert support.SupportInsights is support_models.SupportInsights
    assert support.SupportAdminInbox is support_models.SupportAdminInbox
    assert support.SupportTicketThread is support_models.SupportTicketThread
    assert support.SupportTicketError is support_ticket_flow.SupportTicketError
    assert support.SUPPORT_CANNED_REPLY_PACKS is support_reply_packs.SUPPORT_CANNED_REPLY_PACKS
    assert (
        support.build_support_canned_replies
        is support_reply_packs.build_support_canned_replies
    )
    assert (
        support.build_support_canned_replies_for_pack
        is support_reply_packs.build_support_canned_replies_for_pack
    )
    assert support.SUPPORT_SLA_BUCKET_LABELS is support_catalog.SUPPORT_SLA_BUCKET_LABELS
    assert support.support_waiting_state_label is support_catalog.support_waiting_state_label
    assert support.support_sla_bucket_label is support_catalog.support_sla_bucket_label
    assert support.support_waiting_state is support_sla.support_waiting_state
    assert support.support_sla_bucket is support_sla.support_sla_bucket
    assert support.support_action_lane is support_sla.support_action_lane
    assert support.support_escalation_lane is support_sla.support_escalation_lane
    assert support.support_next_action_label is support_sla.support_next_action_label
    assert support.support_next_action_note is support_sla.support_next_action_note
    assert support.support_next_action_severity is support_sla.support_next_action_severity
    assert (
        support.support_canned_reply_pack_titles
        is support_sla.support_canned_reply_pack_titles
    )
    assert support.support_triage_queue_note is support_sla.support_triage_queue_note
    assert support.create_support_ticket is support_ticket_flow.create_support_ticket
    assert support.add_user_ticket_message is support_ticket_flow.add_user_ticket_message
    assert support.add_admin_ticket_reply is support_ticket_flow.add_admin_ticket_reply
    assert support.close_support_ticket is support_ticket_flow.close_support_ticket
    assert support.reopen_support_ticket is support_ticket_flow.reopen_support_ticket
    assert support.normalize_support_message is support_ticket_flow.normalize_support_message
    assert (
        support._build_support_pack_outcomes
        is support_insight_trends._build_support_pack_outcomes
    )
    assert (
        support._build_support_close_reason_trends
        is support_insight_trends._build_support_close_reason_trends
    )
    assert (
        support._build_support_operator_action_trends
        is support_insight_trends._build_support_operator_action_trends
    )
    assert (
        support._build_support_sla_hotspots
        is support_open_queues._build_support_sla_hotspots
    )
    assert (
        support_open_queues._build_support_sla_hotspots
        is support_sla_queues._build_support_sla_hotspots
    )
    assert (
        support_open_queues._build_support_sla_actions
        is support_sla_queues._build_support_sla_actions
    )
    assert (
        support_open_queues._build_support_sla_action_queue
        is support_sla_queues._build_support_sla_action_queue
    )
    assert (
        support_open_queues._build_support_action_lanes
        is support_sla_queues._build_support_action_lanes
    )
    assert (
        support_open_queues._support_hotspot_kind_for_ticket
        is support_sla_queues._support_hotspot_kind_for_ticket
    )
    assert (
        support_open_queues._support_ticket_queue_rank_key
        is support_queue_ranking._support_ticket_queue_rank_key
    )
    assert (
        support_open_queues._support_top_sample_ticket_ids
        is support_queue_ranking._support_top_sample_ticket_ids
    )
    assert (
        support_open_queues._support_top_lane_sample_ticket_ids
        is support_queue_ranking._support_top_lane_sample_ticket_ids
    )
    assert (
        support._build_support_action_lanes
        is support_open_queues._build_support_action_lanes
    )
    assert (
        support_open_queues._build_support_next_action_queue
        is support_action_queues._build_support_next_action_queue
    )
    assert (
        support_open_queues._build_support_action_routes
        is support_action_queues._build_support_action_routes
    )
    assert (
        support_open_queues._build_support_triage_queue
        is support_action_queues._build_support_triage_queue
    )
    assert (
        support._build_support_triage_queue
        is support_open_queues._build_support_triage_queue
    )
    assert (
        support._build_support_escalation_watchlist
        is support_open_queues._build_support_escalation_watchlist
    )
    assert (
        support_open_queues._build_support_escalation_lanes
        is support_escalation_queues._build_support_escalation_lanes
    )
    assert (
        support_open_queues._build_support_escalation_actions
        is support_escalation_queues._build_support_escalation_actions
    )
    assert (
        support_open_queues._build_support_priority_focus
        is support_escalation_queues._build_support_priority_focus
    )
    assert (
        support_open_queues._build_support_escalation_watchlist
        is support_escalation_queues._build_support_escalation_watchlist
    )
    assert (
        support._build_support_triage_apply_history
        is support_triage_apply._build_support_triage_apply_history
    )
    assert (
        support_triage_apply._build_support_triage_apply_history
        is support_triage_apply_history._build_support_triage_apply_history
    )
    assert (
        support._build_support_triage_apply_routes
        is support_triage_apply._build_support_triage_apply_routes
    )
    assert (
        support_triage_apply._build_support_triage_apply_routes
        is support_triage_apply_core._build_support_triage_apply_routes
    )
    assert (
        support_triage_apply._build_support_triage_apply_actors
        is support_triage_apply_core._build_support_triage_apply_actors
    )
    assert (
        support_triage_apply._build_support_triage_apply_replies
        is support_triage_apply_replies._build_support_triage_apply_replies
    )
    assert (
        support_triage_apply._build_support_triage_apply_actor_replies
        is support_triage_apply_replies._build_support_triage_apply_actor_replies
    )
    assert (
        support_triage_apply._build_support_triage_apply_route_actors
        is support_triage_apply_replies._build_support_triage_apply_route_actors
    )
    assert (
        support_triage_apply._build_support_triage_apply_reply_packs
        is support_triage_apply_combinations._build_support_triage_apply_reply_packs
    )
    assert (
        support_triage_apply._build_support_triage_apply_route_reply_actors
        is support_triage_apply_combinations._build_support_triage_apply_route_reply_actors
    )
    assert (
        support._build_support_triage_apply_effectiveness
        is support_triage_apply._build_support_triage_apply_effectiveness
    )
    assert (
        support_triage_apply._build_support_triage_apply_focus
        is support_triage_apply_rankings._build_support_triage_apply_focus
    )
    assert (
        support_triage_apply._build_support_triage_apply_effectiveness
        is support_triage_apply_rankings._build_support_triage_apply_effectiveness
    )
    assert (
        support_triage_apply._support_triage_apply_route_note
        is support_triage_apply_notes._support_triage_apply_route_note
    )
    assert (
        support_triage_apply._support_triage_apply_route_reply_actor_note
        is support_triage_apply_notes._support_triage_apply_route_reply_actor_note
    )


def test_analytics_module_reexports_model_contracts() -> None:
    assert analytics.AnalyticsSnapshot is analytics_models.AnalyticsSnapshot
    assert analytics.ConversionSourceSnapshot is analytics_models.ConversionSourceSnapshot
    assert analytics.ProductFunnelSnapshot is analytics_models.ProductFunnelSnapshot
    assert analytics.SourceAcquisitionSnapshot is analytics_models.SourceAcquisitionSnapshot
    assert analytics.OfferPerformanceSnapshot is analytics_models.OfferPerformanceSnapshot
    assert analytics.PricingIntelligenceSnapshot is analytics_models.PricingIntelligenceSnapshot
    assert (
        analytics.ProductPairPerformanceSnapshot
        is analytics_models.ProductPairPerformanceSnapshot
    )
    assert (
        analytics.ProductPairCampaignSnapshot is analytics_models.ProductPairCampaignSnapshot
    )
    assert analytics.PromoAttributionSnapshot is analytics_models.PromoAttributionSnapshot
    assert analytics.PromoCampaignSnapshot is analytics_models.PromoCampaignSnapshot
    assert analytics.ReferralAttributionSnapshot is analytics_models.ReferralAttributionSnapshot
    assert analytics.ReferralTopReferrerSnapshot is analytics_models.ReferralTopReferrerSnapshot
    assert (
        analytics.LifecycleCampaignAttributionSnapshot
        is analytics_models.LifecycleCampaignAttributionSnapshot
    )
    assert analytics._percent is analytics_common._percent
    assert analytics._parse_payload is analytics_common._parse_payload
    assert (
        analytics._build_source_campaign_watchlist
        is analytics_lifecycle._build_source_campaign_watchlist
    )
    assert (
        analytics._sorted_source_campaign_items_for_roi
        is analytics_lifecycle._sorted_source_campaign_items_for_roi
    )
    assert analytics._build_product_funnel is analytics_funnel._build_product_funnel
    assert analytics._build_source_funnel is analytics_funnel._build_source_funnel
    assert (
        analytics._build_source_acquisition
        is analytics_acquisition._build_source_acquisition
    )
    assert (
        analytics._build_lifecycle_queue_snapshot
        is analytics_lifecycle_builders._build_lifecycle_queue_snapshot
    )
    assert (
        analytics._build_lifecycle_offer_mix
        is analytics_lifecycle_builders._build_lifecycle_offer_mix
    )
    assert (
        analytics._build_lifecycle_campaign_attribution
        is analytics_lifecycle_builders._build_lifecycle_campaign_attribution
    )
    assert (
        analytics._build_pricing_intelligence
        is analytics_pricing._build_pricing_intelligence
    )
    assert (
        analytics._build_promo_attribution
        is analytics_promo_referral._build_promo_attribution
    )
    assert (
        analytics._build_referral_attribution
        is analytics_promo_referral._build_referral_attribution
    )


def test_web_cabinet_stays_user_facing_after_admin_summary_split() -> None:
    assert not hasattr(web_cabinet, "build_cabinet_admin_summary_payload")
    assert hasattr(web_cabinet, "build_cabinet_bootstrap_payload")
    assert hasattr(web_cabinet, "build_cabinet_profile_payload")
    assert hasattr(
        web_admin_dashboard_summary_sections,
        "build_cabinet_admin_summary_payload",
    )


def test_web_admin_support_sections_reexports_action_layer() -> None:
    assert (
        web_admin_dashboard_support_sections.run_web_admin_support_triage_confirm_action
        is web_admin_dashboard_support_actions.run_web_admin_support_triage_confirm_action
    )
    assert (
        web_admin_dashboard_support_sections.run_web_admin_support_triage_apply_action
        is web_admin_dashboard_support_actions.run_web_admin_support_triage_apply_action
    )


def test_web_admin_support_sections_reuses_ticket_serializers() -> None:
    assert (
        web_admin_dashboard_support_sections._serialize_support_ticket_list_item
        is web_admin_dashboard_support_ticket_serializers._serialize_support_ticket_list_item
    )
    assert (
        web_admin_dashboard_support_sections._serialize_support_close_reason_analytics
        is web_admin_dashboard_support_ticket_serializers._serialize_support_close_reason_analytics
    )
    assert (
        web_admin_dashboard_support_sections._support_queue_counts
        is web_admin_dashboard_support_ticket_serializers._support_queue_counts
    )


def test_web_admin_support_sections_reuses_inbox_section_builders() -> None:
    assert (
        web_admin_dashboard_support_sections.build_web_admin_support_payload
        is web_admin_dashboard_support_inbox_sections.build_web_admin_support_payload
    )
    assert (
        web_admin_dashboard_support_sections._support_overview
        is web_admin_dashboard_support_inbox_sections._support_overview
    )
    assert (
        web_admin_dashboard_support_sections.SUPPORT_FILTERS
        is web_admin_dashboard_support_inbox_sections.SUPPORT_FILTERS
    )
    assert (
        web_admin_dashboard_support_sections.SUPPORT_QUEUE_FILTERS
        is web_admin_dashboard_support_inbox_sections.SUPPORT_QUEUE_FILTERS
    )


def test_web_admin_support_sections_reuses_ticket_section_builders() -> None:
    assert (
        web_admin_dashboard_support_sections.build_web_admin_support_ticket_payload
        is web_admin_dashboard_support_ticket_sections
        .build_web_admin_support_ticket_payload
    )
    assert (
        web_admin_dashboard_support_sections._serialize_support_ticket_triage_batch
        is web_admin_dashboard_support_ticket_sections
        ._serialize_support_ticket_triage_batch
    )


def test_web_admin_support_ticket_serializers_reuses_list_serializers() -> None:
    assert (
        web_admin_dashboard_support_ticket_serializers._serialize_support_ticket_list_item
        is web_admin_dashboard_support_ticket_list_serializers._serialize_support_ticket_list_item
    )
    assert (
        web_admin_dashboard_support_ticket_serializers
        ._serialize_support_close_reason_analytics
        is web_admin_dashboard_support_ticket_list_serializers
        ._serialize_support_close_reason_analytics
    )
    assert (
        web_admin_dashboard_support_ticket_serializers._support_queue_counts
        is web_admin_dashboard_support_ticket_list_serializers._support_queue_counts
    )
    assert (
        web_admin_dashboard_support_ticket_serializers._matches_support_queue
        is web_admin_dashboard_support_ticket_list_serializers._matches_support_queue
    )
    assert (
        web_admin_dashboard_support_ticket_serializers._support_search_blob
        is web_admin_dashboard_support_ticket_list_serializers._support_search_blob
    )
    assert (
        web_admin_dashboard_support_ticket_serializers._support_waiting_state
        is web_admin_dashboard_support_ticket_list_serializers._support_waiting_state
    )


def test_web_admin_support_ticket_serializers_reuses_detail_serializers() -> None:
    assert (
        web_admin_dashboard_support_ticket_serializers
        ._serialize_support_ticket_pinned_context
        is web_admin_dashboard_support_ticket_detail_serializers
        ._serialize_support_ticket_pinned_context
    )
    assert (
        web_admin_dashboard_support_ticket_serializers._serialize_support_next_action
        is web_admin_dashboard_support_ticket_detail_serializers
        ._serialize_support_next_action
    )
    assert (
        web_admin_dashboard_support_ticket_serializers._build_support_operator_hints
        is web_admin_dashboard_support_ticket_detail_serializers
        ._build_support_operator_hints
    )
    assert (
        web_admin_dashboard_support_ticket_serializers._serialize_support_profile_summary
        is web_admin_dashboard_support_ticket_detail_serializers
        ._serialize_support_profile_summary
    )
    assert (
        web_admin_dashboard_support_ticket_serializers._serialize_support_canned_replies
        is web_admin_dashboard_support_ticket_detail_serializers
        ._serialize_support_canned_replies
    )
    assert (
        web_admin_dashboard_support_ticket_serializers._tariff_name
        is web_admin_dashboard_support_ticket_detail_serializers._tariff_name
    )


def test_web_admin_support_sections_reuses_insight_serializer() -> None:
    assert (
        web_admin_dashboard_support_sections._serialize_support_insights
        is web_admin_dashboard_support_insight_serializers._serialize_support_insights
    )


def test_web_admin_support_sections_reuses_insight_section_builders() -> None:
    assert (
        web_admin_dashboard_support_sections.build_web_admin_support_insights_payload
        is web_admin_dashboard_support_insight_sections
        .build_web_admin_support_insights_payload
    )
    live_builder = (
        web_admin_dashboard_support_sections
        ._build_web_admin_support_insights_payload_live
    )
    extracted_live_builder = (
        web_admin_dashboard_support_insight_sections
        ._build_web_admin_support_insights_payload_live
    )
    assert live_builder is extracted_live_builder
    assert (
        web_admin_dashboard_support_sections.SUPPORT_INSIGHT_VIEWS
        is web_admin_dashboard_support_insight_sections.SUPPORT_INSIGHT_VIEWS
    )


def test_web_admin_support_insights_reuses_closed_insight_serializers() -> None:
    assert (
        web_admin_dashboard_support_insight_serializers._serialize_support_distribution
        is web_admin_dashboard_support_closed_insight_serializers._serialize_support_distribution
    )
    close_reason_windows = (
        web_admin_dashboard_support_insight_serializers
        ._serialize_support_close_reason_windows
    )
    extracted_close_reason_windows = (
        web_admin_dashboard_support_closed_insight_serializers
        ._serialize_support_close_reason_windows
    )
    assert close_reason_windows is extracted_close_reason_windows
    pack_outcomes = (
        web_admin_dashboard_support_insight_serializers
        ._serialize_support_canned_reply_pack_outcomes
    )
    extracted_pack_outcomes = (
        web_admin_dashboard_support_closed_insight_serializers
        ._serialize_support_canned_reply_pack_outcomes
    )
    assert pack_outcomes is extracted_pack_outcomes
    recent_summary = (
        web_admin_dashboard_support_insight_serializers
        ._build_support_recent_close_summary
    )
    extracted_recent_summary = (
        web_admin_dashboard_support_closed_insight_serializers
        ._build_support_recent_close_summary
    )
    assert recent_summary is extracted_recent_summary


def test_web_admin_support_insights_reuses_action_insight_serializers() -> None:
    assert (
        web_admin_dashboard_support_insight_serializers._serialize_support_sla_hotspots
        is web_admin_dashboard_support_action_insight_serializers._serialize_support_sla_hotspots
    )
    sla_action_queue = (
        web_admin_dashboard_support_insight_serializers
        ._serialize_support_sla_action_queue
    )
    extracted_sla_action_queue = (
        web_admin_dashboard_support_action_insight_serializers
        ._serialize_support_sla_action_queue
    )
    assert sla_action_queue is extracted_sla_action_queue
    assert (
        web_admin_dashboard_support_insight_serializers._serialize_support_action_routes
        is web_admin_dashboard_support_action_insight_serializers._serialize_support_action_routes
    )
    assert (
        web_admin_dashboard_support_insight_serializers._build_support_sla_queue_summary
        is web_admin_dashboard_support_action_insight_serializers._build_support_sla_queue_summary
    )
    route_summary = (
        web_admin_dashboard_support_insight_serializers
        ._build_support_action_route_summary
    )
    extracted_route_summary = (
        web_admin_dashboard_support_action_insight_serializers
        ._build_support_action_route_summary
    )
    assert route_summary is extracted_route_summary


def test_web_admin_support_insights_reuses_escalation_insight_serializers() -> None:
    assert (
        web_admin_dashboard_support_insight_serializers
        ._serialize_support_escalation_lanes
        is web_admin_dashboard_support_escalation_insight_serializers
        ._serialize_support_escalation_lanes
    )
    assert (
        web_admin_dashboard_support_insight_serializers
        ._serialize_support_priority_focus
        is web_admin_dashboard_support_escalation_insight_serializers
        ._serialize_support_priority_focus
    )
    operator_trends = (
        web_admin_dashboard_support_insight_serializers
        ._serialize_support_operator_action_trends
    )
    extracted_operator_trends = (
        web_admin_dashboard_support_escalation_insight_serializers
        ._serialize_support_operator_action_trends
    )
    assert operator_trends is extracted_operator_trends
    watchlist_summary = (
        web_admin_dashboard_support_insight_serializers
        ._build_support_escalation_watchlist_summary
    )
    extracted_watchlist_summary = (
        web_admin_dashboard_support_escalation_insight_serializers
        ._build_support_escalation_watchlist_summary
    )
    assert watchlist_summary is extracted_watchlist_summary
    action_trend_summary = (
        web_admin_dashboard_support_insight_serializers
        ._build_support_operator_action_trend_summary
    )
    extracted_action_trend_summary = (
        web_admin_dashboard_support_escalation_insight_serializers
        ._build_support_operator_action_trend_summary
    )
    assert action_trend_summary is extracted_action_trend_summary


def test_web_admin_support_sections_reuses_insight_view_registry() -> None:
    assert (
        web_admin_dashboard_support_sections.SUPPORT_INSIGHT_VIEWS
        is web_admin_dashboard_support_insight_views.SUPPORT_INSIGHT_VIEWS
    )
    assert (
        web_admin_dashboard_support_sections._normalize_support_insight_view
        is web_admin_dashboard_support_insight_views._normalize_support_insight_view
    )
    assert (
        web_admin_dashboard_support_sections._support_insight_items_for_view
        is web_admin_dashboard_support_insight_views._support_insight_items_for_view
    )


def test_web_admin_support_insights_reuses_triage_apply_serializers() -> None:
    assert (
        web_admin_dashboard_support_insight_serializers._build_support_triage_views
        is web_admin_dashboard_support_triage_apply_serializers._build_support_triage_views
    )
    assert (
        web_admin_dashboard_support_insight_serializers._build_support_triage_summary_views
        is web_admin_dashboard_support_triage_apply_serializers._build_support_triage_summary_views
    )
    assert (
        web_admin_dashboard_support_insight_serializers._support_triage_confirm_label
        is web_admin_dashboard_support_triage_apply_serializers._support_triage_confirm_label
    )
    insight_coverage_label = (
        web_admin_dashboard_support_insight_serializers
        ._support_triage_apply_effectiveness_coverage_label
    )
    triage_coverage_label = (
        web_admin_dashboard_support_triage_apply_serializers
        ._support_triage_apply_effectiveness_coverage_label
    )
    assert insight_coverage_label is triage_coverage_label


def test_web_admin_support_triage_apply_reuses_queue_serializers() -> None:
    assert (
        web_admin_dashboard_support_triage_apply_serializers._build_support_triage_queue
        is web_admin_dashboard_support_triage_queue_serializers._build_support_triage_queue
    )
    assert (
        web_admin_dashboard_support_triage_apply_serializers._build_support_triage_plans
        is web_admin_dashboard_support_triage_queue_serializers._build_support_triage_plans
    )
    assert (
        web_admin_dashboard_support_triage_apply_serializers._build_support_triage_confirm
        is web_admin_dashboard_support_triage_queue_serializers._build_support_triage_confirm
    )
    assert (
        web_admin_dashboard_support_triage_apply_serializers._support_triage_confirm_note
        is web_admin_dashboard_support_triage_queue_serializers._support_triage_confirm_note
    )


def test_web_admin_support_triage_apply_reuses_view_serializers() -> None:
    apply_views = (
        web_admin_dashboard_support_triage_apply_serializers
        ._build_support_triage_apply_views
    )
    extracted_apply_views = (
        web_admin_dashboard_support_triage_apply_view_serializers
        ._build_support_triage_apply_views
    )
    assert (
        apply_views is extracted_apply_views
    )
    coverage_label = (
        web_admin_dashboard_support_triage_apply_serializers
        ._support_triage_apply_effectiveness_coverage_label
    )
    extracted_coverage_label = (
        web_admin_dashboard_support_triage_apply_view_serializers
        ._support_triage_apply_effectiveness_coverage_label
    )
    assert (
        coverage_label is extracted_coverage_label
    )


def test_web_admin_support_triage_apply_reuses_summary_serializers() -> None:
    summary_views = (
        web_admin_dashboard_support_triage_apply_serializers
        ._build_support_triage_summary_views
    )
    extracted_summary_views = (
        web_admin_dashboard_support_triage_summary_serializers
        ._build_support_triage_summary_views
    )
    assert (
        summary_views is extracted_summary_views
    )
    assert (
        web_admin_dashboard_support_triage_apply_serializers._first_support_triage_item
        is web_admin_dashboard_support_triage_summary_serializers._first_support_triage_item
    )
    assert (
        web_admin_dashboard_support_triage_apply_serializers._support_triage_summary_value
        is web_admin_dashboard_support_triage_summary_serializers._support_triage_summary_value
    )


def test_web_admin_support_triage_summary_reuses_apply_summary_serializers() -> None:
    assert (
        web_admin_dashboard_support_triage_summary_serializers
        ._build_support_triage_apply_summary_views
        is web_admin_dashboard_support_triage_apply_summary_serializers
        ._build_support_triage_apply_summary_views
    )
    assert (
        web_admin_dashboard_support_triage_summary_serializers._first_support_triage_item
        is web_admin_dashboard_support_triage_apply_summary_serializers
        ._first_support_triage_item
    )
    assert (
        web_admin_dashboard_support_triage_summary_serializers
        ._support_triage_summary_value
        is web_admin_dashboard_support_triage_apply_summary_serializers
        ._support_triage_summary_value
    )


def test_web_admin_read_model_sections_reuses_action_layer() -> None:
    assert (
        web_admin_dashboard_read_model_sections._build_read_model_actions_payload_from_watchlist
        is web_admin_dashboard_read_model_actions._build_read_model_actions_payload_from_watchlist
    )
    section_watchlist_builder = (
        web_admin_dashboard_read_model_sections
        ._build_web_admin_read_model_watchlist_from_snapshot_payload
    )
    action_watchlist_builder = (
        web_admin_dashboard_read_model_actions
        ._build_web_admin_read_model_watchlist_from_snapshot_payload
    )
    assert section_watchlist_builder is action_watchlist_builder
    assert (
        web_admin_dashboard_read_model_sections._with_overview_focus
        is web_admin_dashboard_read_model_actions._with_overview_focus
    )


def test_web_admin_read_model_actions_reuse_watchlist_helpers() -> None:
    assert (
        web_admin_dashboard_read_model_actions._positive_leader_item
        is web_admin_dashboard_read_model_watchlist._positive_leader_item
    )
    assert (
        web_admin_dashboard_read_model_actions._improvement_leader_item
        is web_admin_dashboard_read_model_watchlist._improvement_leader_item
    )
    assert (
        web_admin_dashboard_read_model_actions._build_watchlist_item_from_overview
        is web_admin_dashboard_read_model_watchlist._build_watchlist_item_from_overview
    )
    assert (
        web_admin_dashboard_read_model_actions._build_watchlist_item_from_drift
        is web_admin_dashboard_read_model_watchlist._build_watchlist_item_from_drift
    )
    assert (
        web_admin_dashboard_read_model_actions._sort_watchlist_items
        is web_admin_dashboard_read_model_watchlist._sort_watchlist_items
    )


def test_web_admin_read_model_actions_reuse_action_digest_helpers() -> None:
    assert (
        web_admin_dashboard_read_model_actions._build_action_digest_items
        is web_admin_dashboard_read_model_action_digest._build_action_digest_items
    )
    assert (
        web_admin_dashboard_read_model_actions._recommended_read_model_action
        is web_admin_dashboard_read_model_action_digest._recommended_read_model_action
    )
    assert (
        web_admin_dashboard_read_model_actions._read_model_action_category_label
        is web_admin_dashboard_read_model_action_digest._read_model_action_category_label
    )
    assert (
        web_admin_dashboard_read_model_actions._join_labels
        is web_admin_dashboard_read_model_action_digest._join_labels
    )


def test_web_admin_read_model_sections_reuses_descriptor_registry() -> None:
    assert (
        web_admin_dashboard_read_model_sections.ReadModelDescriptor
        is web_admin_dashboard_read_model_descriptors.ReadModelDescriptor
    )
    assert (
        web_admin_dashboard_read_model_sections._all_descriptors
        is web_admin_dashboard_read_model_descriptors._all_descriptors
    )


def test_web_admin_read_model_sections_reuses_serializers() -> None:
    assert (
        web_admin_dashboard_read_model_sections.READ_MODEL_VIEW_OVERVIEW
        is web_admin_dashboard_read_model_serializers.READ_MODEL_VIEW_OVERVIEW
    )
    assert (
        web_admin_dashboard_read_model_sections._build_model_item
        is web_admin_dashboard_read_model_serializers._build_model_item
    )
    assert (
        web_admin_dashboard_read_model_sections._build_drift_item
        is web_admin_dashboard_read_model_serializers._build_drift_item
    )
    assert (
        web_admin_dashboard_read_model_sections._normalize_read_model_view
        is web_admin_dashboard_read_model_serializers._normalize_read_model_view
    )


def test_web_admin_read_model_serializers_reuse_core_helpers() -> None:
    assert (
        web_admin_dashboard_read_model_serializers.READ_MODEL_VIEW_LABELS
        is web_admin_dashboard_read_model_core.READ_MODEL_VIEW_LABELS
    )
    assert (
        web_admin_dashboard_read_model_serializers._decode_payload
        is web_admin_dashboard_read_model_core._decode_payload
    )
    assert (
        web_admin_dashboard_read_model_serializers._int_or_default
        is web_admin_dashboard_read_model_core._int_or_default
    )
    assert (
        web_admin_dashboard_read_model_serializers._read_model_status
        is web_admin_dashboard_read_model_core._read_model_status
    )
    assert (
        web_admin_dashboard_read_model_serializers._read_model_note
        is web_admin_dashboard_read_model_core._read_model_note
    )
    assert (
        web_admin_dashboard_read_model_serializers._read_model_severity
        is web_admin_dashboard_read_model_core._read_model_severity
    )


def test_web_admin_read_model_serializers_reuse_drift_serializers() -> None:
    assert (
        web_admin_dashboard_read_model_serializers._build_drift_item
        is web_admin_dashboard_read_model_drift_serializers._build_drift_item
    )
    assert (
        web_admin_dashboard_read_model_serializers._drift_tone
        is web_admin_dashboard_read_model_drift_serializers._drift_tone
    )


def test_web_admin_read_model_sections_reuses_snapshot_store() -> None:
    assert (
        web_admin_dashboard_read_model_sections._load_snapshot_payload_lookups
        is web_admin_dashboard_read_model_store._load_snapshot_payload_lookups
    )
    assert (
        web_admin_dashboard_read_model_sections._lookup_descriptor_snapshot
        is web_admin_dashboard_read_model_store._lookup_descriptor_snapshot
    )


def test_web_admin_read_model_sections_reexports_live_builders() -> None:
    assert (
        web_admin_dashboard_read_model_sections._build_web_admin_read_models_payload_live
        is web_admin_dashboard_read_model_live._build_web_admin_read_models_payload_live
    )
    assert (
        web_admin_dashboard_read_model_sections._build_web_admin_read_model_drift_payload_live
        is web_admin_dashboard_read_model_live._build_web_admin_read_model_drift_payload_live
    )
    assert (
        web_admin_dashboard_read_model_sections._build_live_descriptor_payload
        is web_admin_dashboard_read_model_live._build_live_descriptor_payload
    )


def test_web_admin_read_model_live_reuses_descriptor_dispatcher() -> None:
    assert (
        web_admin_dashboard_read_model_live._build_live_descriptor_payload
        is web_admin_dashboard_read_model_live_descriptors
        ._build_live_descriptor_payload
    )
    assert (
        web_admin_dashboard_read_model_live._build_live_admin_analytics_text_payload
        is web_admin_dashboard_read_model_live_descriptors
        ._build_live_admin_analytics_text_payload
    )
    assert (
        web_admin_dashboard_read_model_live._build_live_admin_analytics_text_body
        is web_admin_dashboard_read_model_live_descriptors
        ._build_live_admin_analytics_text_body
    )


def test_web_admin_read_model_live_reuses_overview_builder() -> None:
    assert (
        web_admin_dashboard_read_model_live._build_web_admin_read_models_payload_live
        is web_admin_dashboard_read_model_live_overview
        ._build_web_admin_read_models_payload_live
    )


def test_web_admin_lifecycle_sections_reexports_live_builder() -> None:
    assert (
        web_admin_dashboard_lifecycle_sections.LIFECYCLE_VIEWS
        is web_admin_dashboard_lifecycle_live.LIFECYCLE_VIEWS
    )
    assert (
        web_admin_dashboard_lifecycle_sections._build_web_admin_lifecycle_payload_live
        is web_admin_dashboard_lifecycle_live._build_web_admin_lifecycle_payload_live
    )


def test_web_admin_lifecycle_live_reuses_source_serializers() -> None:
    assert (
        web_admin_dashboard_lifecycle_live._build_lifecycle_source_view_items
        is web_admin_dashboard_lifecycle_source_serializers
        ._build_lifecycle_source_view_items
    )


def test_web_admin_lifecycle_live_reuses_attribution_serializers() -> None:
    assert (
        web_admin_dashboard_lifecycle_live._build_lifecycle_attribution_view_items
        is web_admin_dashboard_lifecycle_attribution_serializers
        ._build_lifecycle_attribution_view_items
    )


def test_web_admin_lifecycle_sections_reexports_serializers() -> None:
    assert (
        web_admin_dashboard_lifecycle_sections._serialize_lifecycle_offer_mix
        is web_admin_dashboard_lifecycle_serializers._serialize_lifecycle_offer_mix
    )
    assert (
        web_admin_dashboard_lifecycle_sections._serialize_lifecycle_campaign_attribution
        is web_admin_dashboard_lifecycle_serializers._serialize_lifecycle_campaign_attribution
    )


def test_web_admin_lifecycle_serializers_reuse_campaign_source_serializers() -> None:
    assert (
        web_admin_dashboard_lifecycle_serializers
        ._serialize_lifecycle_source_roi_items
        is web_admin_dashboard_lifecycle_campaign_source_serializers
        ._serialize_lifecycle_source_roi_items
    )
    assert (
        web_admin_dashboard_lifecycle_serializers
        ._serialize_lifecycle_source_opportunity_items
        is web_admin_dashboard_lifecycle_campaign_source_serializers
        ._serialize_lifecycle_source_opportunity_items
    )
    assert (
        web_admin_dashboard_lifecycle_serializers
        ._serialize_lifecycle_source_action_items
        is web_admin_dashboard_lifecycle_campaign_source_serializers
        ._serialize_lifecycle_source_action_items
    )
    assert (
        web_admin_dashboard_lifecycle_serializers
        ._serialize_lifecycle_source_highlight_items
        is web_admin_dashboard_lifecycle_campaign_source_serializers
        ._serialize_lifecycle_source_highlight_items
    )
    assert (
        web_admin_dashboard_lifecycle_serializers
        ._serialize_lifecycle_source_watchlist_items
        is web_admin_dashboard_lifecycle_campaign_source_serializers
        ._serialize_lifecycle_source_watchlist_items
    )
    assert (
        web_admin_dashboard_lifecycle_serializers
        ._serialize_lifecycle_source_campaign_items
        is web_admin_dashboard_lifecycle_campaign_source_serializers
        ._serialize_lifecycle_source_campaign_items
    )


def test_web_admin_analytics_sections_reexports_serializers() -> None:
    assert (
        web_admin_dashboard_analytics_sections._serialize_pricing_intelligence_detail
        is web_admin_dashboard_analytics_serializers._serialize_pricing_intelligence_detail
    )
    assert (
        web_admin_dashboard_analytics_sections._serialize_offer_inventory_preview
        is web_admin_dashboard_analytics_serializers._serialize_offer_inventory_preview
    )
    assert (
        web_admin_dashboard_analytics_sections._serialize_promo_attribution_summary
        is web_admin_dashboard_analytics_serializers._serialize_promo_attribution_summary
    )


def test_admin_read_model_reporting_reexports_models() -> None:
    assert (
        admin_read_model_reporting.AdminReadModelAlertSummary
        is admin_read_model_reporting_models.AdminReadModelAlertSummary
    )
    assert (
        admin_read_model_reporting.AdminReadModelDriftSummary
        is admin_read_model_reporting_models.AdminReadModelDriftSummary
    )
    assert (
        admin_read_model_reporting.AdminReadModelOperatorDigest
        is admin_read_model_reporting_models.AdminReadModelOperatorDigest
    )


def test_admin_read_model_reporting_reexports_summary_builders() -> None:
    assert (
        admin_read_model_reporting._build_alert_summary
        is admin_read_model_reporting_summaries._build_alert_summary
    )
    assert (
        admin_read_model_reporting._build_drift_summary
        is admin_read_model_reporting_summaries._build_drift_summary
    )
    assert (
        admin_read_model_reporting._build_action_summary
        is admin_read_model_reporting_summaries._build_action_summary
    )
    assert (
        admin_read_model_reporting._build_watchlist_summary
        is admin_read_model_reporting_summaries._build_watchlist_summary
    )


def test_admin_read_model_reporting_reexports_digest_builders() -> None:
    assert (
        admin_read_model_reporting.build_admin_read_model_watchlist_digest
        is admin_read_model_reporting_digests.build_admin_read_model_watchlist_digest
    )
    assert (
        admin_read_model_reporting.build_admin_read_model_action_digest
        is admin_read_model_reporting_digests.build_admin_read_model_action_digest
    )
    assert (
        admin_read_model_reporting.build_admin_read_model_drift_digest
        is admin_read_model_reporting_digests.build_admin_read_model_drift_digest
    )
    assert (
        admin_read_model_reporting.build_admin_read_model_focus_summary
        is admin_read_model_reporting_digests.build_admin_read_model_focus_summary
    )
    assert (
        admin_read_model_reporting.build_admin_read_model_snapshot_operator_payload
        is admin_read_model_reporting_digests.build_admin_read_model_snapshot_operator_payload
    )


def test_admin_read_model_reporting_reexports_async_loaders() -> None:
    assert (
        admin_read_model_reporting.load_admin_read_model_alert_summary
        is admin_read_model_reporting_loaders.load_admin_read_model_alert_summary
    )
    assert (
        admin_read_model_reporting.build_admin_read_model_drift_summary
        is admin_read_model_reporting_loaders.build_admin_read_model_drift_summary
    )
    assert (
        admin_read_model_reporting.build_admin_read_model_action_summary
        is admin_read_model_reporting_loaders.build_admin_read_model_action_summary
    )
    assert (
        admin_read_model_reporting.build_admin_read_model_watchlist_summary
        is admin_read_model_reporting_loaders.build_admin_read_model_watchlist_summary
    )
