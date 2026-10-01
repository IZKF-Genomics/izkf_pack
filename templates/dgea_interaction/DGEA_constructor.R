#!/usr/bin/env Rscript

source("dgea_interaction_inputs.R")
source("DGEA_functions.R")

dir.create(results_dir, recursive = TRUE, showWarnings = FALSE)
dir.create(file.path(results_dir, "tables"), recursive = TRUE, showWarnings = FALSE)
dir.create(file.path(results_dir, "figures"), recursive = TRUE, showWarnings = FALSE)
dir.create("reports", recursive = TRUE, showWarnings = FALSE)
dir.create(file.path("reports", "comparisons"), recursive = TRUE, showWarnings = FALSE)

cfg <- read_analysis_config("config/analysis.yaml")
metadata <- read_sample_metadata("config/samples.csv")
imported <- import_gene_counts(salmon_dir, tx2gene_file, metadata, application)
gene_counts <- imported$counts
annotation <- imported$annotation
validate_analysis_inputs(gene_counts, metadata, cfg)

write_csv_table(metadata, file.path(results_dir, "tables", "sample_inventory.csv"))
write_csv_table(
  tibble(
    source = salmon_dir,
    tx2gene = tx2gene_file,
    counts_from_abundance = imported$counts_from_abundance,
    n_samples = ncol(gene_counts),
    n_features_raw = nrow(gene_counts),
    total_counts = sum(gene_counts),
    organism = organism
  ),
  file.path(results_dir, "tables", "input_summary.csv")
)

filtered <- filter_counts(gene_counts, cfg$analysis$min_count, cfg$analysis$min_samples)
write_csv_table(
  tibble(
    min_count = cfg$analysis$min_count,
    min_samples = cfg$analysis$min_samples,
    n_features_raw = nrow(gene_counts),
    n_features_retained = nrow(filtered),
    fraction_retained = nrow(filtered) / nrow(gene_counts)
  ),
  file.path(results_dir, "tables", "filter_summary.csv")
)
make_qc_outputs(filtered, metadata, cfg, annotation, results_dir)

fits <- list()
summaries <- list()
for (contrast in cfg$contrasts) {
  message("Fitting contrast: ", contrast$id)
  fit <- fit_contrast(filtered, metadata, contrast, cfg, annotation)
  fits[[contrast$id]] <- list(fit = fit, contrast = contrast)
  summaries[[contrast$id]] <- write_contrast_outputs(fit, contrast, cfg, results_dir)
}
contrast_summary <- bind_rows(summaries) |>
  mutate(is_primary = contrast_id == cfg$analysis$primary_contrast)
write_csv_table(contrast_summary, file.path(results_dir, "tables", "contrast_summary.csv"))
write_results_workbook(fits, file.path(results_dir, "tables", "gene_differential_results.xlsx"))

sr_response <- classify_response(fits, "ttn_sr_response_interaction", "wt_sr_vs_control", "ttn_sr_vs_control", cfg, results_dir)
af_response <- classify_response(fits, "ttn_af_response_interaction", "wt_af_vs_sr", "ttn_af_vs_sr", cfg, results_dir)
response_summaries <- bind_rows(sr_response$summary, af_response$summary)
response_details <- list(
  ttn_sr_response_interaction = sr_response$details,
  ttn_af_response_interaction = af_response$details
)
write_csv_table(response_summaries, file.path(results_dir, "tables", "response_class_summary.csv"))
pathway_results <- run_pathway_analysis(fits, organism, cfg, results_dir)
write_comparison_workbooks(fits, pathway_results, response_details, cfg, results_dir)
write_interpretation_payload(
  fits, contrast_summary, response_summaries, pathway_results,
  file.path(results_dir, "interpretation_data.json")
)

primary <- fits[[cfg$analysis$primary_contrast]]
if (is.null(primary)) stopf("Configured primary_contrast was not fitted: %s", cfg$analysis$primary_contrast)
top_ids <- primary$fit$results |> filter(!is.na(padj)) |> slice_head(n = 25) |> pull(gene_id)
primary_norm <- counts(primary$fit$dds, normalized = TRUE)[top_ids, , drop = FALSE] |>
  as.data.frame() |>
  rownames_to_column("gene_id") |>
  left_join(annotation |> rename(gene_symbol = gene_name), by = "gene_id") |>
  relocate(gene_symbol, .before = gene_id)
write_csv_table(primary_norm, file.path(results_dir, "tables", "top_primary_normalized_counts.csv"))

runtime <- list(
  template = "dgea_interaction",
  engine = "DESeq2",
  command = "Rscript DGEA_constructor.R",
  config = normalizePath("config/analysis.yaml"),
  samples = normalizePath("config/samples.csv"),
  salmon_dir = salmon_dir,
  counts_from_abundance = imported$counts_from_abundance,
  contrasts = vapply(cfg$contrasts, `[[`, character(1), "id")
)
writeLines(jsonlite::toJSON(runtime, auto_unbox = TRUE, pretty = TRUE), file.path(results_dir, "runtime_command.json"))
validate_output_completeness(cfg, root = results_dir)
message("Statistical analysis completed; interpretation and report rendering follow.")
