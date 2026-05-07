####################################################################
# DGEA_constructor.R
# Main analyst-facing control surface for DGEA workspaces rendered by
# Linkar. Edit this file to reorganize samples, define comparisons,
# and enable optional reports.
####################################################################

source("dgea_inputs.R")
source("DGEA_functions.R")

library(dplyr)
library(readr)
library(tibble)
library(tidyr)

dir.create(results_dir, recursive = TRUE, showWarnings = FALSE)

samplesheet <- read.csv(samplesheet_path, stringsAsFactors = FALSE)
if (!"sample" %in% names(samplesheet)) {
  stop("Samplesheet must contain a 'sample' column.", call. = FALSE)
}

# BEGIN CONFIGURED SAMPLE METADATA
# No configured sample metadata. Edit this block or run ./run.sh --configure.
# The constructor will use an existing 'group' column if present.
# END CONFIGURED SAMPLE METADATA

if (!"group" %in% names(samplesheet)) {
  message("No 'group' column found. The all-samples overview can still run, but pairwise reports require sample metadata. Run ./run.sh --configure or edit DGEA_constructor.R manually.")
}

workspace_dir <- getwd()

global_config <- list(
  workspace_dir = workspace_dir,
  results_dir = results_dir,
  samplesheet = samplesheet,
  samplesheet_path = samplesheet_path,
  salmon_dir = salmon_dir,
  tx2gene_file = tx2gene_file,
  application = application,
  organism = organism,
  spikein = spikein,
  name = project_name,
  authors = authors,
  design_formula = "~ group",
  go = TRUE,
  gsea = TRUE,
  cutoff_adj_p = 0.05,
  cutoff_log2fc = 1,
  pvalueCutoff_GO = 0.05,
  pvalueCutoff_GSEA = 0.05,
  highlighted_genes = NULL
)

check_missing_dirs(c(global_config$salmon_dir))

# Always render the all-samples overview.
render_DGEA_all_sample(global_config)

# Define comparisons below. Each entry is regular R, so you can filter samples,
# relabel groups, change the design, or toggle enrichment per comparison.
# Useful fields:
# - name: optional report label
# - base_group / target_group: required for pairwise DGEA
# - samplesheet: optional replacement sample table
# - design_formula, go, gsea, cutoffs: optional overrides
# Use ./run.sh --configure to generate this block from an interactive terminal.
# BEGIN CONFIGURED COMPARISONS
comparisons <- list()
# END CONFIGURED COMPARISONS

# Example custom comparison:
# comparisons <- list(
#   list(
#     name = "treated_vs_control_without_outlier",
#     samplesheet = subset(samplesheet, sample != "bad_sample_01"),
#     base_group = "control",
#     target_group = "treated",
#     design_formula = "~ batch + group",
#     go = TRUE,
#     gsea = FALSE
#   )
# )

for (comparison in comparisons) {
  report_config <- modifyList(global_config, comparison)
  if (is.null(report_config$samplesheet)) {
    report_config$samplesheet <- samplesheet
  }
  if (is.null(report_config$base_group) || is.null(report_config$target_group)) {
    stop("Each comparison must define base_group and target_group.", call. = FALSE)
  }
  if (!is.null(report_config$name) && nzchar(report_config$name)) {
    report_config$additional_tag <- report_config$name
  }
  render_DGEA_report(report_config)
}
