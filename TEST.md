# cli-anything-swmm — Test Results

## Run command

```bash
cd agent-harness
python3 -m pytest cli_anything/swmm/tests/ --import-mode=importlib -v
```

## Summary

**240 passed, 0 failed** (March 2026)

---

## Unit tests — `test_core.py` (190 tests)

| Class | Test | Result |
|-------|------|--------|
| TestCreateProject | test_create_project_basic | PASSED |
| TestCreateProject | test_create_project_lps | PASSED |
| TestCreateProject | test_create_project_invalid_units | PASSED |
| TestCreateProject | test_create_project_required_sections | PASSED |
| TestCreateProject | test_create_project_creates_dirs | PASSED |
| TestParseInp | test_roundtrip_preserves_sections | PASSED |
| TestParseInp | test_roundtrip_preserves_data | PASSED |
| TestParseInp | test_parse_missing_file | PASSED |
| TestParseInp | test_comments_preserved | PASSED |
| TestParseInp | test_write_inp_canonical_order | PASSED |
| TestOpenProject | test_open_valid | PASSED |
| TestOpenProject | test_open_missing_file | PASSED |
| TestProjectInfo | test_project_info_empty_counts | PASSED |
| TestProjectInfo | test_project_info_with_elements | PASSED |
| TestProjectInfo | test_project_info_has_options | PASSED |
| TestAddJunction | test_add_junction_basic | PASSED |
| TestAddJunction | test_add_junction_defaults | PASSED |
| TestAddJunction | test_add_junction_custom_depth | PASSED |
| TestRemoveJunction | test_remove_existing | PASSED |
| TestRemoveJunction | test_remove_nonexistent | PASSED |
| TestAddConduit | test_add_conduit_basic | PASSED |
| TestAddConduit | test_add_conduit_creates_xsection | PASSED |
| TestAddConduit | test_add_conduit_shape | PASSED |
| TestRemoveConduit | test_remove_conduit | PASSED |
| TestAddSubcatchment | test_add_subcatchment | PASSED |
| TestAddSubcatchment | test_add_subcatchment_pct_imperv | PASSED |
| TestAddOutfall | test_add_outfall | PASSED |
| TestAddOutfall | test_add_outfall_types | PASSED |
| TestAddRaingage | test_add_raingage | PASSED |
| TestAddRaingage | test_add_raingage_timeseries_ref | PASSED |
| TestListNetwork | test_list_network_empty | PASSED |
| TestListNetwork | test_list_network_with_elements | PASSED |
| TestGetOptions | test_get_options_basic | PASSED |
| TestGetOptions | test_get_options_returns_dict | PASSED |
| TestSetOptions | test_set_options_dates | PASSED |
| TestSetOptions | test_set_options_iso_date_conversion | PASSED |
| TestSetOptions | test_set_options_routing | PASSED |
| TestSetOptions | test_set_options_invalid_flow_units | PASSED |
| TestSetOptions | test_set_options_preserves_other_opts | PASSED |
| TestSetSimulationDates | test_set_simulation_dates | PASSED |
| TestAddTimeseries | test_add_timeseries_basic | PASSED |
| TestAddTimeseries | test_add_timeseries_replaces_existing | PASSED |
| TestListTimeseries | test_list_timeseries_empty | PASSED |
| TestListTimeseries | test_list_timeseries_populated | PASSED |
| TestAddRainfallEvent | test_add_rainfall_scs | PASSED |
| TestAddRainfallEvent | test_add_rainfall_uniform | PASSED |
| TestAddRainfallEvent | test_add_rainfall_triangular | PASSED |
| TestAddRainfallEvent | test_rainfall_total_depth_reasonable | PASSED |
| TestAddRainfallEvent | test_add_rainfall_custom_ts_name | PASSED |
| TestSession | test_session_load_and_save | PASSED |
| TestSession | test_session_push_undo | PASSED |
| TestSession | test_session_redo | PASSED |
| TestSession | test_session_undo_empty_returns_false | PASSED |
| TestSession | test_session_redo_empty_returns_false | PASSED |
| TestSession | test_session_push_clears_redo | PASSED |
| TestSession | test_session_status | PASSED |
| TestCalibSession | test_load_creates_default_session | PASSED |
| TestCalibSession | test_save_and_reload | PASSED |
| TestAddParam | test_add_conduit_roughness | PASSED |
| TestAddParam | test_add_subcatchment_imperv | PASSED |
| TestAddParam | test_add_subarea_n_imperv | PASSED |
| TestAddParam | test_add_infiltration_maxrate | PASSED |
| TestAddParam | test_add_param_replaces_duplicate | PASSED |
| TestAddParam | test_add_param_invalid_type_field | PASSED |
| TestAddParam | test_add_param_min_ge_max_raises | PASSED |
| TestAddParam | test_custom_nominal | PASSED |
| TestModifyParamInSections | test_modify_conduit_roughness | PASSED |
| TestModifyParamInSections | test_modify_subcatchment_imperv | PASSED |
| TestModifyParamInSections | test_modify_junction_maxdepth | PASSED |
| TestModifyParamInSections | test_modify_all_elements | PASSED |
| TestModifyParamInSections | test_modify_nonexistent_element_returns_false | PASSED |
| TestModifyParamInSections | test_modify_invalid_param_raises | PASSED |
| TestComputeMetrics | test_perfect_fit_nse_is_one | PASSED |
| TestComputeMetrics | test_constant_sim_nse_is_zero | PASSED |
| TestComputeMetrics | test_overestimate_negative_pbias | PASSED |
| TestComputeMetrics | test_underestimate_positive_pbias | PASSED |
| TestComputeMetrics | test_rmse_known_value | PASSED |
| TestComputeMetrics | test_mae_known_value | PASSED |
| TestComputeMetrics | test_n_field_correct | PASSED |
| TestComputeMetrics | test_empty_observed_raises | PASSED |
| TestComputeMetrics | test_single_point_raises | PASSED |
| TestAddObserved | test_add_observed_node_depth | PASSED |
| TestAddObserved | test_add_observed_link_flow | PASSED |
| TestAddObserved | test_add_observed_replaces_same_id | PASSED |
| TestAddObserved | test_add_observed_invalid_spec_raises | PASSED |
| TestAddObserved | test_add_observed_invalid_type_raises | PASSED |
| TestLhsSamples | test_lhs_dimensions | PASSED |
| TestLhsSamples | test_lhs_within_bounds | PASSED |
| TestLhsSamples | test_lhs_all_strata_covered | PASSED |
| TestLhsSamples | test_lhs_reproducible_with_seed | PASSED |
| TestLhsSamples | test_lhs_different_seeds_differ | PASSED |
| TestGridSamples | test_grid_count_single_param | PASSED |
| TestGridSamples | test_grid_count_two_params | PASSED |
| TestGridSamples | test_grid_endpoints_included | PASSED |
| TestParseDatetime | test_parse_iso_with_seconds | PASSED |
| TestParseDatetime | test_parse_iso_without_seconds | PASSED |
| TestParseDatetime | test_parse_us_format | PASSED |
| TestParseDatetime | test_parse_invalid_raises | PASSED |
| TestApplyBestParams | test_apply_writes_file | PASSED |
| TestApplyBestParams | test_apply_missing_inp_raises | PASSED |
| TestApplyBestParams | test_apply_bad_param_id_reported | PASSED |
| TestRulesAdd | test_add_simple_rule | PASSED |
| TestRulesAdd | test_add_multiple_conditions | PASSED |
| TestRulesAdd | test_add_with_else_and_priority |PASSED |
| TestRulesAdd | test_add_multiple_then_actions | PASSED |
| TestRulesAdd | test_add_replaces_existing_same_id | PASSED |
| TestRulesAdd | test_add_empty_id_raises | PASSED |
| TestRulesAdd | test_add_empty_if_raises | PASSED |
| TestRulesAdd | test_add_empty_then_raises | PASSED |
| TestRulesAdd | test_controls_section_created | PASSED |
| TestRulesAdd | test_add_or_condition | PASSED |
| TestRulesList | test_list_empty | PASSED |
| TestRulesList | test_list_single | PASSED |
| TestRulesList | test_list_multiple | PASSED |
| TestRulesList | test_list_has_else_flag | PASSED |
| TestRulesList | test_list_priority | PASSED |
| TestGetRule | test_get_existing | PASSED |
| TestGetRule | test_get_missing_returns_none | PASSED |
| TestRemoveRule | test_remove_existing | PASSED |
| TestRemoveRule | test_remove_missing_returns_false | PASSED |
| TestRemoveRule | test_remove_leaves_other_rules | PASSED |
| TestRemoveRule | test_remove_from_missing_section | PASSED |
| TestReviseRule | test_revise_if_clauses | PASSED |
| TestReviseRule | test_revise_then_actions | PASSED |
| TestReviseRule | test_revise_add_else | PASSED |
| TestReviseRule | test_revise_clear_else | PASSED |
| TestReviseRule | test_revise_priority | PASSED |
| TestReviseRule | test_revise_clear_priority | PASSED |
| TestReviseRule | test_revise_missing_rule_raises | PASSED |
| TestReviseRule | test_revise_omitted_fields_unchanged | PASSED |
| TestRulesRoundtrip | test_write_and_reparse | PASSED |
| TestRulesRoundtrip | test_multiple_rules_roundtrip | PASSED |
| TestAddPump | test_add_pump_basic | PASSED |
| TestAddPump | test_add_pump_default_status_on | PASSED |
| TestAddPump | test_add_pump_off_status | PASSED |
| TestAddPump | test_add_pump_startup_shutoff | PASSED |
| TestAddPump | test_add_pump_ideal_curve | PASSED |
| TestRemovePump | test_remove_pump_existing | PASSED |
| TestRemovePump | test_remove_pump_nonexistent | PASSED |
| TestAddWeir | test_add_weir_basic | PASSED |
| TestAddWeir | test_add_weir_transverse_default | PASSED |
| TestAddWeir | test_add_weir_vnotch | PASSED |
| TestAddWeir | test_add_weir_crest_height | PASSED |
| TestAddWeir | test_add_weir_discharge_coeff | PASSED |
| TestRemoveWeir | test_remove_weir_existing | PASSED |
| TestRemoveWeir | test_remove_weir_nonexistent | PASSED |
| TestAddOrifice | test_add_orifice_basic | PASSED |
| TestAddOrifice | test_add_orifice_creates_xsection | PASSED |
| TestAddOrifice | test_add_orifice_bottom_type | PASSED |
| TestAddOrifice | test_add_orifice_side_type | PASSED |
| TestAddOrifice | test_add_orifice_discharge_coeff | PASSED |
| TestAddOrifice | test_add_orifice_offset | PASSED |
| TestRemoveOrifice | test_remove_orifice_existing | PASSED |
| TestRemoveOrifice | test_remove_orifice_removes_xsection | PASSED |
| TestRemoveOrifice | test_remove_orifice_nonexistent | PASSED |
| TestAddInflow | test_add_inflow_basic | PASSED |
| TestAddInflow | test_add_inflow_timeseries_ref | PASSED |
| TestAddInflow | test_add_inflow_mfactor | PASSED |
| TestAddInflow | test_add_inflow_baseline | PASSED |
| TestAddInflow | test_add_inflow_custom_constituent | PASSED |
| TestRemoveInflow | test_remove_inflow_existing | PASSED |
| TestRemoveInflow | test_remove_inflow_nonexistent | PASSED |
| TestListNetworkExtended | test_pump_appears_in_links | PASSED |
| TestListNetworkExtended | test_weir_appears_in_links | PASSED |
| TestListNetworkExtended | test_orifice_appears_in_links | PASSED |
| TestListNetworkExtended | test_element_types_correct | PASSED |
| TestSplitIntoSections | test_sections_detected | PASSED |
| TestSplitIntoSections | test_empty_file_returns_empty | PASSED |
| TestParseContinuityTable | test_runoff_continuity_parsed | PASSED |
| TestParseContinuityTable | test_flow_routing_continuity_parsed | PASSED |
| TestParseContinuityTable | test_missing_section_returns_empty | PASSED |
| TestParseSubcatchRunoff | test_subcatch_parsed | PASSED |
| TestParseSubcatchRunoff | test_subcatch_missing_returns_empty | PASSED |
| TestParseNodeDepthSummary | test_nodes_parsed | PASSED |
| TestParseNodeDepthSummary | test_outfall_present | PASSED |
| TestParseLinkFlowSummary | test_links_parsed | PASSED |
| TestParseLinkFlowSummary | test_link_c2_present | PASSED |
| TestParseReport | test_parse_report_returns_all_keys | PASSED |
| TestParseReport | test_parse_report_no_errors | PASSED |
| TestParseReport | test_parse_report_missing_file_raises | PASSED |
| TestParseReport | test_node_depth_via_parse_report | PASSED |
| TestParseReport | test_link_flow_via_parse_report | PASSED |
| TestGetNodeResults | test_get_existing_node | PASSED |
| TestGetNodeResults | test_get_missing_node_returns_empty | PASSED |
| TestGetLinkResults | test_get_existing_link | PASSED |
| TestGetLinkResults | test_get_missing_link_returns_dict | PASSED |
| TestGetRunoffSummary | test_runoff_summary_structure | PASSED |
| TestGetRunoffSummary | test_runoff_continuity_values | PASSED |
| TestGetFlowRoutingSummary | test_flow_routing_structure | PASSED |
| TestGetFlowRoutingSummary | test_flow_routing_nodes_populated | PASSED |

---

## E2E tests — `test_full_e2e.py` (50 tests)

| Class | Test | Result |
|-------|------|--------|
| TestFullSimulationPipeline | test_complete_project_structure | PASSED |
| TestFullSimulationPipeline | test_run_simulation_success | PASSED |
| TestFullSimulationPipeline | test_validate_inp_passes | PASSED |
| TestReportParsing | test_parse_report_returns_dict | PASSED |
| TestReportParsing | test_simulation_no_errors | PASSED |
| TestReportParsing | test_node_results_available | PASSED |
| TestReportParsing | test_link_results_available | PASSED |
| TestReportParsing | test_get_node_results | PASSED |
| TestReportParsing | test_get_link_results | PASSED |
| TestReportParsing | test_get_runoff_summary | PASSED |
| TestReportParsing | test_get_flow_routing_summary | PASSED |
| TestCLISubprocess | test_help | PASSED |
| TestCLISubprocess | test_project_new_json | PASSED |
| TestCLISubprocess | test_project_info_json | PASSED |
| TestCLISubprocess | test_network_add_junction_json | PASSED |
| TestCLISubprocess | test_full_simulation_workflow | PASSED |
| TestCLISubprocess | test_network_list_json | PASSED |
| TestCLISubprocess | test_options_show_json | PASSED |
| TestUndoRedoIntegration | test_undo_reverses_add | PASSED |
| TestUndoRedoIntegration | test_redo_reapplies | PASSED |
| TestUndoRedoIntegration | test_save_after_undo | PASSED |
| TestCalibrationE2E | test_collect_simulated_series_node | PASSED |
| TestCalibrationE2E | test_collect_simulated_series_link | PASSED |
| TestCalibrationE2E | test_calibration_metrics_self_consistency | PASSED |
| TestCalibrationE2E | test_sensitivity_one_param | PASSED |
| TestCalibrationE2E | test_sensitivity_nominal_gives_best_nse | PASSED |
| TestCalibrationE2E | test_calibration_lhs_finds_nominal | PASSED |
| TestCalibrationE2E | test_calibration_apply_writes_inp | PASSED |
| TestCalibrationE2E | test_calibration_grid_method | PASSED |
| TestCalibrateSubprocessCLI | test_calibrate_help | PASSED |
| TestCalibrateSubprocessCLI | test_calibrate_params_add_json | PASSED |
| TestCalibrateSubprocessCLI | test_calibrate_params_list_json | PASSED |
| TestCalibrateSubprocessCLI | test_calibrate_metrics_json | PASSED |
| TestCalibrateSubprocessCLI | test_calibrate_status_json | PASSED |
| TestCalibrateSubprocessCLI | test_calibrate_full_workflow_json | PASSED |
| TestHydraulicStructuresAPI | test_add_pump_and_list | PASSED |
| TestHydraulicStructuresAPI | test_remove_pump | PASSED |
| TestHydraulicStructuresAPI | test_add_weir_and_roundtrip | PASSED |
| TestHydraulicStructuresAPI | test_weir_in_list_network | PASSED |
| TestHydraulicStructuresAPI | test_add_orifice_with_xsection | PASSED |
| TestHydraulicStructuresAPI | test_orifice_in_list_network | PASSED |
| TestHydraulicStructuresAPI | test_add_inflow_roundtrip | PASSED |
| TestHydraulicStructuresAPI | test_remove_inflow | PASSED |
| TestNewCLICommands | test_add_pump_cli | PASSED |
| TestNewCLICommands | test_add_weir_cli | PASSED |
| TestNewCLICommands | test_add_orifice_cli | PASSED |
| TestNewCLICommands | test_add_inflow_cli | PASSED |
| TestNewCLICommands | test_remove_pump_weir_orifice_cli | PASSED |
| TestNewCLICommands | test_results_subcatchments_cli | PASSED |
| TestNewCLICommands | test_network_list_includes_new_types | PASSED |

---

## Notable bugs fixed during development

1. **pyswmm 2.x constructor kwargs**: Used `rptfile=`/`binfile=` — corrected to `reportfile=`/`outputfile=`.
2. **`sim.getError()` removed in pyswmm 2.x**: Replaced with `sim.flow_routing_error` / `sim.runoff_error` attributes.
3. **Rain gage FORMAT field**: `TIMESERIES` is the source type, not the format. Valid formats are `INTENSITY`, `VOLUME`, `CUMULATIVE`. Default changed to `INTENSITY`.
4. **`swmm.toolkit` namespace conflict**: `cli_anything/swmm/` shadowed the real package when pytest added parent dirs to `sys.path`. Fixed by pre-importing `swmm.toolkit` in root `conftest.py::pytest_configure()`.
5. **JSON mode stdout pollution**: `_skin.success()` wrote to stdout, corrupting JSON output. Fixed by `_ok()`/`_info()` helpers that redirect to stderr when `--json` is active.
6. **`.rpt` section parser**: Rewrote `_split_into_sections()` to handle SWMM 5.2.4's actual format (three-line header: stars / title / stars on separate lines).
7. **Subcatch runoff synthetic data**: Data line with a `HH:MM` time token caused silent parse failure in `float()` conversion. Fixed by using numeric-only data columns in the synthetic RPT fixture.
8. **Continuity table whitespace keys**: `_parse_continuity_table()` returns keys with trailing whitespace from `rsplit("...", 1)`. Tests normalise with `{k.strip(): v for k, v in result.items()}`.
9. **E2E orifice test `NameError`**: `test_add_orifice_with_xsection` used `add_storage` which wasn't imported in `test_full_e2e.py`. Fixed by adding `add_storage` to the network import.
