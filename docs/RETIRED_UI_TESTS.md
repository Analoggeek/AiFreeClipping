# Retired-feature UI tests

These tests assert the explicitly removed four-step/manual editor/Director UI.
They are retired, not passed or skipped. Their backend/render/transport coverage
remains where applicable. New clean clipping/model/crop tests replace the product
acceptance surface. Counts from the old release must not be compared as though
all removed feature tests passed.

- `tests/test_workflow_v251.py::test_dragging_player_then_gameplay_preserves_both_live_overlays`
- `tests/test_workflow_v251.py::test_layout_and_caption_preferences_survive_refresh_and_navigation`
- `tests/test_workflow_v251.py::test_camera_source_preset_updates_both_regions_and_real_preview`
- `tests/test_workflow_v251.py::test_export_existing_render_is_not_blocked_by_changed_recipe_or_invalid_crop`
- `tests/test_workflow_v251.py::test_source_video_sink_updates_canvas_from_real_playback`
- `tests/test_workflow_v251.py::test_drag_updates_composition_before_mouse_release_and_small_click_rolls_back`
- `tests/test_workflow_v251.py::test_review_refresh_cannot_steal_source_playback`
- `tests/test_reference_dashboard.py::test_dashboard_styles_sync_settings_and_preserve_explicit_import`
- `tests/test_reference_dashboard.py::test_dashboard_stacks_at_narrow_width_and_guards_project_steps`
- `tests/test_reference_dashboard.py::test_media_bin_uses_real_metadata_and_selects_existing_item`
- `tests/test_reference_dashboard.py::test_settings_section_navigation_preserves_preferences`
- `tests/test_pro_workspace.py::test_all_destinations_and_sidebar_persistence`
- `tests/test_pro_workspace.py::test_caption_preview_is_a_real_ffmpeg_frame`
- `tests/test_pro_customization.py::test_studio_defaults_and_named_custom_profile_reopen`
- `tests/test_pro_customization.py::test_native_inspector_canvas_and_layout_actions`
- `tests/test_overlay_tracks.py::test_native_add_edit_overlay_buttons_and_inspector`
- `tests/test_multitrack.py::test_native_widget_actions_edit_save_reopen_and_decode_real_frames`
- `tests/test_multitrack.py::test_native_keyframe_controls_drive_model_recovery_and_undo`
- `tests/test_multitrack.py::test_native_waveform_worker_delivers_real_envelope_without_blocking_ui`
- `tests/test_workflow_v25.py::test_wizard_replaces_gaming_navigation_and_upload_controls`
- `tests/test_workflow_v25.py::test_real_one_click_import_edit_review_export_flow`
- `tests/test_performance_release.py::test_busy_remains_true_until_queued_gui_completion_is_handled`
- `tests/test_performance_release.py::test_startup_is_lazy_and_workspace_is_removed_without_deleting_projects`
- `tests/test_tightening.py::test_editor_review_applies_only_after_confirmation_and_checks_source`
- `tests/test_gemma_director.py::test_plan_repair_is_bounded_and_does_not_execute_bad_output`
- `tests/test_gemma_director.py::test_director_history_survives_reopen_and_protects_newer_manual_settings`
- `tests/test_gemma_director.py::test_context_marks_missing_analysis_and_bounds_candidates`
- `tests/test_gemma_director.py::test_retired_pages_and_dashboard_share_real_workflow`
- `tests/test_gemma_director.py::test_typed_timeline_commands_are_real_undoable_and_persist`
- `tests/test_gemma_director.py::test_invalid_timeline_plans_never_partially_apply`
- `tests/test_gemma_director.py::test_stale_or_destructive_director_plan_refused`
- `tests/test_gemma_director.py::test_approved_timeline_commands_really_render_captioned_output`
- `tests/test_gemma_director.py::test_dashboard_director_history_updates_actual_controls`
- `tests/test_local_editing_agent.py::test_unsupported_or_unbounded_edits_rejected`
- `tests/test_local_editing_agent.py::test_outside_or_invalid_ranges_rejected`
- `tests/test_local_editing_agent.py::test_approved_plan_updates_real_project_atomically_and_preserves_crops`
- `tests/test_local_editing_agent.py::test_transaction_failure_rolls_back_settings_and_project`
- `tests/test_local_editing_agent.py::test_model_output_is_data_not_executable_instructions`
- `tests/test_local_editing_agent.py::test_layout_plans_activate_supported_recipe_and_reject_conflicts`
- `tests/test_local_editing_agent.py::test_real_plan_render_and_delivery_without_python_external_connections`
- `tests/test_local_editing_agent.py::test_ui_approval_modifies_actual_project_not_just_chat`
- `tests/test_local_editing_agent.py::test_edit_cannot_implicitly_download_models_even_with_legacy_flag`

- `tests/test_longform_preferences.py::test_native_longform_plan_edit_save_reopen` (legacy longform format/backend tests remain).
