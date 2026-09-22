#!/usr/bin/env Rscript

source("mirna_inputs.R")
source("miRNA_functions.R")

dir.create(results_dir, recursive = TRUE, showWarnings = FALSE)
dir.create(file.path(results_dir, "tables"), recursive = TRUE, showWarnings = FALSE)
dir.create(file.path(results_dir, "figures"), recursive = TRUE, showWarnings = FALSE)
dir.create("reports", recursive = TRUE, showWarnings = FALSE)
dir.create(file.path("reports", "comparisons"), recursive = TRUE, showWarnings = FALSE)

cfg <- read_analysis_config("config/analysis.yaml")
metadata <- read_sample_metadata("config/samples.csv")
counts <- read_nfcore_count_matrix(counts_file, metadata$sample)
counts <- counts[, metadata$sample, drop = FALSE]
validate_analysis_inputs(counts, metadata, cfg)

write_csv_table(metadata, file.path(results_dir, "tables", "sample_inventory.csv"))
input_summary <- tibble(
  dataset = "mature",
  source_file = counts_file,
  input_orientation = attr(counts, "input_orientation") %||% "unknown",
  n_samples = ncol(counts),
  n_features_raw = nrow(counts),
  total_counts = sum(counts),
  organism = organism
)
write_csv_table(input_summary, file.path(results_dir, "tables", "input_summary.csv"))

filtered <- filter_counts(counts, cfg$analysis$min_count, cfg$analysis$min_samples)
filter_summary <- tibble(
  min_count = cfg$analysis$min_count,
  min_samples = cfg$analysis$min_samples,
  n_features_raw = nrow(counts),
  n_features_retained = nrow(filtered),
  fraction_retained = nrow(filtered) / nrow(counts)
)
write_csv_table(filter_summary, file.path(results_dir, "tables", "filter_summary.csv"))
make_qc_outputs(filtered, metadata, cfg, results_dir)

fits <- list()
summaries <- list()
for (contrast in cfg$contrasts) {
  message("Fitting contrast: ", contrast$id)
  fit <- fit_contrast(filtered, metadata, contrast, cfg)
  fits[[contrast$id]] <- list(fit = fit, contrast = contrast)
  summaries[[contrast$id]] <- write_contrast_outputs(fit, contrast, cfg, results_dir)
}
contrast_summary <- bind_rows(summaries)
contrast_summary$is_primary <- contrast_summary$contrast_id == cfg$analysis$primary_contrast
write_csv_table(contrast_summary, file.path(results_dir, "tables", "contrast_summary.csv"))
make_agreement_plot(fits, cfg, results_dir)
write_results_workbook(fits, file.path(results_dir, "tables", "miRNA_differential_results.xlsx"))

primary <- fits[[cfg$analysis$primary_contrast]]
if (is.null(primary)) stopf("Configured primary_contrast was not fitted: %s", cfg$analysis$primary_contrast)
top_ids <- primary$fit$results |> filter(!is.na(padj)) |> slice_head(n = 25) |> pull(mirna_id)
primary_norm <- counts(primary$fit$dds, normalized = TRUE)[top_ids, , drop = FALSE] |>
  as.data.frame() |>
  rownames_to_column("mirna_id")
write_csv_table(primary_norm, file.path(results_dir, "tables", "top_primary_normalized_counts.csv"))

hairpin_enabled <- isTRUE(cfg$supplementary$analyze_hairpin)
hairpin_status <- tibble(enabled = hairpin_enabled, available = nzchar(hairpin_counts_file) && file.exists(hairpin_counts_file), note = "")
if (hairpin_enabled && !hairpin_status$available) {
  hairpin_status$note <- "Hairpin analysis was requested, but no hairpin count file was available."
} else if (!hairpin_enabled) {
  hairpin_status$note <- "Hairpin analysis is disabled; mature-miRNA results are the primary analysis."
} else {
  hairpin_root <- file.path(results_dir, "hairpin")
  hairpin_counts <- read_nfcore_count_matrix(hairpin_counts_file, metadata$sample)
  hairpin_counts <- hairpin_counts[, metadata$sample, drop = FALSE]
  hairpin_filtered <- filter_counts(hairpin_counts, cfg$analysis$min_count, cfg$analysis$min_samples)
  write_csv_table(metadata, file.path(hairpin_root, "tables", "sample_inventory.csv"))
  write_csv_table(
    tibble(
      dataset = "hairpin",
      source_file = hairpin_counts_file,
      n_samples = ncol(hairpin_counts),
      n_features_raw = nrow(hairpin_counts),
      n_features_retained = nrow(hairpin_filtered),
      total_counts = sum(hairpin_counts)
    ),
    file.path(hairpin_root, "tables", "input_summary.csv")
  )
  make_qc_outputs(hairpin_filtered, metadata, cfg, hairpin_root)
  hairpin_fits <- list()
  hairpin_summaries <- list()
  for (contrast in cfg$contrasts) {
    message("Fitting supplementary hairpin contrast: ", contrast$id)
    fit <- fit_contrast(hairpin_filtered, metadata, contrast, cfg)
    hairpin_fits[[contrast$id]] <- list(fit = fit, contrast = contrast)
    hairpin_summaries[[contrast$id]] <- write_contrast_outputs(fit, contrast, cfg, hairpin_root)
  }
  hairpin_contrast_summary <- bind_rows(hairpin_summaries)
  hairpin_contrast_summary$is_primary <- hairpin_contrast_summary$contrast_id == cfg$analysis$primary_contrast
  write_csv_table(hairpin_contrast_summary, file.path(hairpin_root, "tables", "contrast_summary.csv"))
  make_agreement_plot(hairpin_fits, cfg, hairpin_root)
  write_results_workbook(hairpin_fits, file.path(hairpin_root, "tables", "hairpin_differential_results.xlsx"))
  validate_output_completeness(cfg, root = hairpin_root)
  hairpin_status$note <- "Hairpin counts were filtered, normalized, and modeled independently as a supplementary analysis."
}
write_csv_table(hairpin_status, file.path(results_dir, "tables", "hairpin_status.csv"))

runtime <- list(
  template = "mirna_differential",
  engine = "DESeq2",
  command = "Rscript miRNA_constructor.R",
  config = normalizePath("config/analysis.yaml"),
  samples = normalizePath("config/samples.csv"),
  counts = counts_file,
  contrasts = vapply(cfg$contrasts, `[[`, character(1), "id")
)
writeLines(jsonlite::toJSON(runtime, auto_unbox = TRUE, pretty = TRUE), file.path(results_dir, "runtime_command.json"))

validate_output_completeness(cfg, root = results_dir)
status <- system2("quarto", c("render", "miRNA_differential_report.qmd", "--output-dir", "reports"))
if (!identical(status, 0L)) stopf("Quarto report rendering failed with exit status %s.", status)
report_path <- file.path("reports", "miRNA_differential_report.html")
validate_output_completeness(cfg, report_path = report_path, root = results_dir)
dir.create(file.path("reports", "comparisons"), recursive = TRUE, showWarnings = FALSE)
for (contrast in cfg$contrasts) {
  comparison_report <- file.path("reports", "comparisons", paste0(contrast$id, ".html"))
  message("Rendering comparison report: ", contrast$id)
  status <- system2(
    "quarto",
    c(
      "render", "miRNA_contrast_report.qmd",
      "--output", paste0(contrast$id, ".html"),
      "--output-dir", file.path("reports", "comparisons"),
      "--no-clean"
    ),
    env = paste0("MIRNA_CONTRAST_ID=", contrast$id)
  )
  if (!identical(status, 0L)) stopf("Quarto comparison report rendering failed for %s with exit status %s.", contrast$id, status)
  if (!file.exists(comparison_report) || file.info(comparison_report)$size <= 0) stopf("Comparison report was not created: %s", comparison_report)
}
# Quarto copies source figures beside the output even though embed-resources has
# already placed them inside each HTML file. Remove only that generated duplicate.
embedded_resource_copies <- c(
  file.path("reports", "results"),
  file.path("reports", "comparisons", "results")
)
for (path in embedded_resource_copies) {
  if (dir.exists(path)) unlink(path, recursive = TRUE, force = TRUE)
}
message("miRNA differential analysis completed: ", report_path)
