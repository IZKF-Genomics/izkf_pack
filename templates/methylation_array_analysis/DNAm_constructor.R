####################################################################
# DNAm_constructor.R
# Main analyst-facing control surface for the methylation_array_analysis
# workspace rendered by Linkar.
####################################################################

source("dnam_inputs.R")
source("DNAm_functions.R")

ensure_dirs(".")

cfg <- load_project_config("config/datasets.toml")
samples <- load_samples("config/samples.csv")
global_config <- build_global_config(
  cfg = cfg,
  samples = samples,
  authors = authors,
  project_name = project_name
)

# Optional analyst overrides belong here. Keep the stable study-wide defaults
# in config/datasets.toml and use this file for ad hoc analysis adjustments.
# Example:
# cfg$batch_correction$enabled <- FALSE
# global_config$delta_beta_min <- 0.15
# global_config$use_batch_corrected <- FALSE

# Define one standalone report per comparison. Each entry may override the
# samples, covariates, thresholds, correction usage, enrichment, or drilldown
# settings for just that comparison.
active_samples <- samples |>
  dplyr::filter(parse_bool_vec(.data$include, default = TRUE))

# Optional: define a focused cohort for the overview-only embeddings shown in
# 03_batch_diagnostics.qmd. Leave this as all active samples unless you have a
# clear reporting subset to highlight.
overview_samples <- active_samples
global_config$overview_samples <- overview_samples

# Add study-specific comparisons here.
# Minimal example:
# comparisons <- list(
#   list(
#     name = "groupA_vs_groupB",
#     samples = active_samples |>
#       dplyr::filter(.data$group %in% c("groupA", "groupB")),
#     target_group = "groupA",
#     base_group = "groupB",
#     use_batch_corrected = TRUE,
#     dmr_enabled = TRUE,
#     enrichment_enabled = TRUE
#   )
# )
comparisons <- list()

if (!identical(Sys.getenv("DNAM_SKIP_RUN"), "1")) {
  validate_workspace(cfg, samples)
  run_methylation_study(global_config, comparisons)
}
