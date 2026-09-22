suppressPackageStartupMessages({
  library(DESeq2)
  library(dplyr)
  library(tidyr)
  library(tibble)
  library(readr)
  library(ggplot2)
  library(ggrepel)
  library(scales)
  library(yaml)
  library(openxlsx)
  library(htmltools)
  library(knitr)
})

`%||%` <- function(x, y) if (is.null(x) || length(x) == 0) y else x

stopf <- function(...) stop(sprintf(...), call. = FALSE)

read_analysis_config <- function(path = "config/analysis.yaml") {
  if (!file.exists(path)) stopf("Analysis config not found: %s", path)
  cfg <- yaml::read_yaml(path)
  if (!identical(as.integer(cfg$schema_version), 1L)) stopf("Unsupported analysis config schema_version.")
  cfg
}

read_sample_metadata <- function(path = "config/samples.csv") {
  if (!file.exists(path)) stopf("Sample metadata not found: %s", path)
  metadata <- readr::read_csv(path, show_col_types = FALSE, col_types = cols(.default = col_character()))
  required <- c("sample", "include", "group", "time", "subject")
  missing <- setdiff(required, names(metadata))
  if (length(missing)) stopf("Sample metadata is missing: %s", paste(missing, collapse = ", "))
  metadata <- metadata |>
    mutate(include = tolower(include) %in% c("true", "1", "yes", "y")) |>
    filter(include)
  if (!nrow(metadata)) stopf("No samples are enabled in config/samples.csv.")
  if (anyDuplicated(metadata$sample)) stopf("Enabled sample names must be unique.")
  if (any(!complete.cases(metadata[, c("sample", "group", "time", "subject")]))) {
    stopf("Enabled sample metadata contains missing values.")
  }
  metadata$subject_nested <- interaction(metadata$group, metadata$subject, drop = TRUE, sep = "_")
  metadata
}

read_nfcore_count_matrix <- function(path, sample_names) {
  if (!file.exists(path)) stopf("Count file not found: %s", path)
  raw <- read.csv(path, row.names = 1, check.names = FALSE, stringsAsFactors = FALSE)
  if (all(sample_names %in% rownames(raw))) {
    matrix <- t(as.matrix(raw[sample_names, , drop = FALSE]))
    orientation <- "samples_by_rows"
  } else if (all(sample_names %in% colnames(raw))) {
    matrix <- as.matrix(raw[, sample_names, drop = FALSE])
    orientation <- "features_by_rows"
  } else {
    stopf("Configured samples do not match either axis of %s.", path)
  }
  storage.mode(matrix) <- "numeric"
  if (any(!is.finite(matrix)) || any(matrix < 0) || any(matrix != round(matrix))) {
    stopf("Count matrix must contain finite, non-negative integer counts.")
  }
  if (anyDuplicated(rownames(matrix))) stopf("Count matrix contains duplicate miRNA identifiers.")
  attr(matrix, "input_orientation") <- orientation
  round(matrix)
}

validate_analysis_inputs <- function(counts, metadata, cfg) {
  if (!identical(colnames(counts), metadata$sample)) stopf("Count columns and metadata rows are not aligned.")
  a <- cfg$analysis
  required <- c("alpha", "lfc_threshold", "min_count", "min_samples", "top_labels", "top_heatmap")
  missing <- required[!vapply(required, function(key) !is.null(a[[key]]), logical(1))]
  if (length(missing)) stopf("Missing analysis settings: %s", paste(missing, collapse = ", "))
  if (a$alpha <= 0 || a$alpha >= 1) stopf("alpha must be between zero and one.")
  if (!length(cfg$contrasts)) stopf("At least one contrast must be configured.")
  ids <- vapply(cfg$contrasts, `[[`, character(1), "id")
  if (anyDuplicated(ids)) stopf("Contrast ids must be unique.")
  invisible(TRUE)
}

theme_report <- function() {
  theme_minimal(base_size = 13) +
    theme(
      plot.title = element_text(face = "bold", size = 16),
      plot.subtitle = element_text(color = "#4A4A4A"),
      axis.title = element_text(face = "bold"),
      panel.grid.minor = element_blank(),
      legend.position = "top",
      plot.margin = margin(10, 14, 10, 10)
    )
}

group_palette <- function(groups) {
  base <- c("#0072B2", "#D55E00", "#009E73", "#CC79A7", "#E69F00", "#56B4E9")
  stats::setNames(base[seq_along(groups)], groups)
}

save_plot_all <- function(plot, stem, width = 9, height = 6) {
  dir.create(dirname(stem), recursive = TRUE, showWarnings = FALSE)
  ggsave(paste0(stem, ".png"), plot, width = width, height = height, dpi = 320, bg = "white")
  ggsave(paste0(stem, ".pdf"), plot, width = width, height = height, device = grDevices::pdf, bg = "white")
  ggsave(paste0(stem, ".svg"), plot, width = width, height = height, device = grDevices::svg, bg = "white")
  invisible(stem)
}

write_csv_table <- function(x, path) {
  dir.create(dirname(path), recursive = TRUE, showWarnings = FALSE)
  readr::write_csv(as_tibble(x), path, na = "")
  invisible(path)
}

assert_full_rank <- function(formula, coldata, label) {
  matrix <- model.matrix(formula, data = as.data.frame(coldata))
  if (qr(matrix)$rank < ncol(matrix)) {
    stopf("Model matrix for '%s' is not full rank (%d/%d).", label, qr(matrix)$rank, ncol(matrix))
  }
  matrix
}

filter_counts <- function(counts, min_count, min_samples) {
  keep <- rowSums(counts >= min_count) >= min_samples
  if (sum(keep) < 2) stopf("Filtering retained fewer than two miRNAs; revise min_count/min_samples.")
  counts[keep, , drop = FALSE]
}

prepare_dds <- function(counts, metadata, design, label) {
  metadata <- as.data.frame(metadata)
  rownames(metadata) <- metadata$sample
  assert_full_rank(design, metadata, label)
  dds <- suppressMessages(DESeqDataSetFromMatrix(countData = counts[, metadata$sample, drop = FALSE], colData = metadata, design = design))
  DESeq(dds, quiet = TRUE)
}

result_frame <- function(res, shrunk, contrast, cfg) {
  output <- as.data.frame(res) |>
    rownames_to_column("mirna_id") |>
    transmute(
      mirna_id,
      baseMean,
      log2FoldChange,
      lfcSE,
      conf_low = log2FoldChange - qnorm(0.975) * lfcSE,
      conf_high = log2FoldChange + qnorm(0.975) * lfcSE,
      stat,
      pvalue,
      padj
    )
  shrink_df <- as.data.frame(shrunk) |>
    rownames_to_column("mirna_id") |>
    select(mirna_id, shrunken_log2FoldChange = log2FoldChange)
  output <- output |>
    left_join(shrink_df, by = "mirna_id") |>
    mutate(
      contrast_id = contrast$id,
      contrast_label = contrast$label,
      contrast_type = contrast$type,
      direction = case_when(
        shrunken_log2FoldChange > 0 ~ "positive",
        shrunken_log2FoldChange < 0 ~ "negative",
        TRUE ~ "zero"
      ),
      fdr_significant = !is.na(padj) & padj < cfg$analysis$alpha,
      evidence_threshold = fdr_significant & abs(shrunken_log2FoldChange) >= cfg$analysis$lfc_threshold
    ) |>
    arrange(is.na(padj), padj, desc(abs(shrunken_log2FoldChange)))
  output
}

fit_contrast <- function(filtered_counts, metadata, contrast, cfg) {
  kind <- contrast$type
  if (kind == "interaction") {
    keep <- metadata$group %in% c(contrast$base_group, contrast$target_group) &
      metadata$time %in% c(contrast$base_time, contrast$target_time)
    md <- droplevels(metadata[keep, , drop = FALSE])
    md$group <- relevel(factor(md$group), contrast$base_group)
    md$time <- relevel(factor(md$time), contrast$base_time)
    md$subject_nested <- factor(interaction(md$group, md$subject, drop = TRUE, sep = "_"))
    md$group_time_interaction <- as.integer(
      md$group == contrast$target_group & md$time == contrast$target_time
    )
    design <- ~ subject_nested + time + group_time_interaction
    dds <- prepare_dds(filtered_counts[, md$sample, drop = FALSE], md, design, contrast$id)
    interaction_names <- resultsNames(dds)[grepl("group_time_interaction", resultsNames(dds), fixed = TRUE)]
    if (length(interaction_names) != 1) {
      stopf("Expected one interaction coefficient for '%s'; found: %s", contrast$id, paste(interaction_names, collapse = ", "))
    }
    res <- results(dds, name = interaction_names[[1]], alpha = cfg$analysis$alpha)
    shrunk <- lfcShrink(dds, coef = interaction_names[[1]], res = res, type = "normal", quiet = TRUE)
    model_formula <- "~ subject_nested + time + group_time_interaction"
    coefficient <- interaction_names[[1]]
  } else if (kind == "paired_time") {
    keep <- metadata$group == contrast$group & metadata$time %in% c(contrast$base_time, contrast$target_time)
    md <- droplevels(metadata[keep, , drop = FALSE])
    md$time <- relevel(factor(md$time), contrast$base_time)
    md$subject_nested <- factor(md$subject_nested)
    design <- ~ subject_nested + time
    dds <- prepare_dds(filtered_counts[, md$sample, drop = FALSE], md, design, contrast$id)
    contrast_vector <- c("time", contrast$target_time, contrast$base_time)
    res <- results(dds, contrast = contrast_vector, alpha = cfg$analysis$alpha)
    shrunk <- lfcShrink(dds, contrast = contrast_vector, res = res, type = "normal", quiet = TRUE)
    model_formula <- "~ subject_nested + time"
    coefficient <- paste(contrast_vector, collapse = ":")
  } else if (kind == "two_group") {
    keep <- metadata$time == contrast$at_time & metadata$group %in% c(contrast$base_group, contrast$target_group)
    md <- droplevels(metadata[keep, , drop = FALSE])
    md$group <- relevel(factor(md$group), contrast$base_group)
    design <- ~ group
    dds <- prepare_dds(filtered_counts[, md$sample, drop = FALSE], md, design, contrast$id)
    contrast_vector <- c("group", contrast$target_group, contrast$base_group)
    res <- results(dds, contrast = contrast_vector, alpha = cfg$analysis$alpha)
    shrunk <- lfcShrink(dds, contrast = contrast_vector, res = res, type = "normal", quiet = TRUE)
    model_formula <- "~ group"
    coefficient <- paste(contrast_vector, collapse = ":")
  } else {
    stopf("Unsupported contrast type: %s", kind)
  }
  list(
    dds = dds,
    metadata = md,
    results = result_frame(res, shrunk, contrast, cfg),
    model_formula = model_formula,
    coefficient = coefficient
  )
}

select_labels <- function(results, n) {
  results |>
    filter(!is.na(padj), !is.na(shrunken_log2FoldChange)) |>
    arrange(desc(evidence_threshold), padj, desc(abs(shrunken_log2FoldChange))) |>
    slice_head(n = n)
}

plot_ma <- function(results, contrast, cfg) {
  ggplot(filter(results, baseMean > 0), aes(baseMean, shrunken_log2FoldChange, color = evidence_threshold)) +
    geom_point(alpha = 0.65, size = 1.8) +
    geom_hline(yintercept = c(-1, 1) * cfg$analysis$lfc_threshold, linetype = 2, color = "#666666") +
    scale_x_log10(labels = label_number()) +
    scale_color_manual(values = c(`FALSE` = "#A8A8A8", `TRUE` = "#D55E00"), guide = "none") +
    labs(title = "MA plot", subtitle = contrast$label, x = "Mean normalized count", y = "Shrunken log2 fold change") +
    theme_report()
}

plot_volcano <- function(results, contrast, cfg) {
  plot_df <- results |> filter(!is.na(padj), !is.na(shrunken_log2FoldChange)) |> mutate(minus_log10_fdr = -log10(pmax(padj, .Machine$double.xmin)))
  labels <- select_labels(plot_df, cfg$analysis$top_labels)
  ggplot(plot_df, aes(shrunken_log2FoldChange, minus_log10_fdr, color = evidence_threshold)) +
    geom_point(alpha = 0.68, size = 1.9) +
    geom_vline(xintercept = c(-1, 1) * cfg$analysis$lfc_threshold, linetype = 2, color = "#666666") +
    geom_hline(yintercept = -log10(cfg$analysis$alpha), linetype = 2, color = "#666666") +
    geom_text_repel(data = labels, aes(label = mirna_id), size = 3, max.overlaps = Inf, box.padding = 0.4) +
    scale_color_manual(values = c(`FALSE` = "#A8A8A8", `TRUE` = "#D55E00"), guide = "none") +
    labs(title = "Volcano plot", subtitle = contrast$label, x = "Shrunken log2 fold change", y = expression(-log[10](FDR))) +
    theme_report()
}

plot_forest <- function(results, contrast) {
  top <- results |>
    filter(!is.na(padj), !is.na(conf_low), !is.na(conf_high)) |>
    arrange(desc(evidence_threshold), padj, desc(abs(log2FoldChange))) |>
    slice_head(n = 20) |>
    arrange(log2FoldChange) |>
    mutate(mirna_id = factor(mirna_id, levels = mirna_id))
  ggplot(top, aes(log2FoldChange, mirna_id, color = evidence_threshold)) +
    geom_vline(xintercept = 0, color = "#777777", linewidth = 0.4) +
    geom_errorbar(aes(xmin = conf_low, xmax = conf_high), orientation = "y", width = 0.18) +
    geom_point(size = 2.4) +
    scale_color_manual(values = c(`FALSE` = "#0072B2", `TRUE` = "#D55E00"), guide = "none") +
    labs(title = "Effect-size forest plot", subtitle = paste(contrast$label, "- raw Wald estimates and 95% CI"), x = "Log2 fold change", y = NULL) +
    theme_report()
}

plot_heatmap <- function(dds, results, contrast, cfg) {
  chosen <- results |>
    filter(!is.na(padj)) |>
    arrange(desc(evidence_threshold), padj, desc(abs(shrunken_log2FoldChange))) |>
    slice_head(n = cfg$analysis$top_heatmap) |>
    pull(mirna_id)
  normalized <- log2(counts(dds, normalized = TRUE)[chosen, , drop = FALSE] + 1)
  z <- t(scale(t(normalized)))
  z[!is.finite(z)] <- 0
  long <- as.data.frame(z) |>
    rownames_to_column("mirna_id") |>
    pivot_longer(-mirna_id, names_to = "sample", values_to = "z_score")
  md <- as.data.frame(colData(dds)) |> rownames_to_column("sample_key")
  long <- long |> left_join(md |> select(sample_key, sample, group, time), by = c("sample" = "sample_key"))
  long$sample_label <- factor(paste(long$sample, long$group, long$time, sep = " | "), levels = unique(paste(md$sample, md$group, md$time, sep = " | ")))
  long$mirna_id <- factor(long$mirna_id, levels = rev(chosen))
  ggplot(long, aes(sample_label, mirna_id, fill = z_score)) +
    geom_tile(color = "white", linewidth = 0.1) +
    scale_fill_gradient2(low = "#2166AC", mid = "white", high = "#B2182B", midpoint = 0, limits = c(-3, 3), oob = squish) +
    labs(title = "Top-miRNA expression heatmap", subtitle = contrast$label, x = NULL, y = NULL, fill = "Row z-score") +
    theme_report() + theme(axis.text.x = element_text(angle = 55, hjust = 1, size = 8), legend.position = "right")
}

write_contrast_outputs <- function(fit, contrast, cfg, root = "results") {
  table_path <- file.path(root, "tables", "contrasts", paste0(contrast$id, ".csv"))
  write_csv_table(fit$results, table_path)
  stem <- file.path(root, "figures", "contrasts", contrast$id)
  save_plot_all(plot_ma(fit$results, contrast, cfg), paste0(stem, "_ma"))
  save_plot_all(plot_volcano(fit$results, contrast, cfg), paste0(stem, "_volcano"))
  save_plot_all(plot_forest(fit$results, contrast), paste0(stem, "_forest"), width = 9, height = 7)
  save_plot_all(plot_heatmap(fit$dds, fit$results, contrast, cfg), paste0(stem, "_heatmap"), width = 12, height = 9)
  data.frame(
    contrast_id = contrast$id,
    contrast_label = contrast$label,
    contrast_type = contrast$type,
    model_formula = fit$model_formula,
    coefficient = fit$coefficient,
    n_samples = ncol(fit$dds),
    n_features_tested = sum(!is.na(fit$results$pvalue)),
    n_fdr_significant = sum(fit$results$fdr_significant, na.rm = TRUE),
    n_evidence_threshold = sum(fit$results$evidence_threshold, na.rm = TRUE),
    min_fdr = if (all(is.na(fit$results$padj))) NA_real_ else min(fit$results$padj, na.rm = TRUE),
    result_table = table_path,
    stringsAsFactors = FALSE
  )
}

make_qc_outputs <- function(counts, metadata, cfg, root = "results") {
  dds <- suppressMessages(DESeqDataSetFromMatrix(countData = counts, colData = data.frame(row.names = metadata$sample), design = ~ 1))
  dds <- estimateSizeFactors(dds)
  normalized <- counts(dds, normalized = TRUE)
  vsd <- varianceStabilizingTransformation(dds, blind = TRUE)
  transformed <- assay(vsd)
  library <- tibble(
    sample = colnames(counts),
    library_size = colSums(counts),
    detected_mirnas = colSums(counts > 0)
  ) |> left_join(metadata, by = "sample")
  write_csv_table(library, file.path(root, "tables", "sample_qc.csv"))
  write_csv_table(as.data.frame(normalized) |> rownames_to_column("mirna_id"), file.path(root, "tables", "normalized_counts.csv"))

  palette <- group_palette(unique(metadata$group))
  p_library <- ggplot(library, aes(reorder(sample, library_size), library_size, fill = group)) +
    geom_col(width = 0.75) + coord_flip() + scale_fill_manual(values = palette) +
    scale_y_continuous(labels = label_number()) +
    labs(title = "Raw library size", subtitle = "Total mature-miRNA counts before normalization", x = NULL, y = "Counts", fill = "Group") + theme_report()
  save_plot_all(p_library, file.path(root, "figures", "qc", "library_size"), width = 9, height = 6.5)

  p_detected <- ggplot(library, aes(reorder(sample, detected_mirnas), detected_mirnas, fill = group)) +
    geom_col(width = 0.75) + coord_flip() + scale_fill_manual(values = palette) +
    labs(title = "Detected mature miRNAs", subtitle = "Number with at least one raw count", x = NULL, y = "Detected miRNAs", fill = "Group") + theme_report()
  save_plot_all(p_detected, file.path(root, "figures", "qc", "detected_mirnas"), width = 9, height = 6.5)

  pca <- prcomp(t(transformed))
  percent <- 100 * pca$sdev^2 / sum(pca$sdev^2)
  pca_df <- as.data.frame(pca$x[, 1:2, drop = FALSE]) |> rownames_to_column("sample") |> left_join(metadata, by = "sample")
  write_csv_table(pca_df, file.path(root, "tables", "pca_coordinates.csv"))
  p_pca <- ggplot(pca_df, aes(PC1, PC2, color = group, shape = time, label = sample)) +
    geom_point(size = 3.2) + geom_text_repel(size = 3, max.overlaps = Inf) + scale_color_manual(values = palette) +
    labs(title = "PCA of variance-stabilized counts", subtitle = "No confidence ellipse is shown because the study is small", x = sprintf("PC1 (%.1f%%)", percent[1]), y = sprintf("PC2 (%.1f%%)", percent[2]), color = "Group", shape = "Time") + theme_report()
  save_plot_all(p_pca, file.path(root, "figures", "qc", "pca"), width = 9, height = 7)

  correlations <- cor(transformed, method = "spearman")
  corr_long <- as.data.frame(correlations) |> rownames_to_column("sample_x") |> pivot_longer(-sample_x, names_to = "sample_y", values_to = "correlation")
  write_csv_table(corr_long, file.path(root, "tables", "sample_correlations.csv"))
  p_corr <- ggplot(corr_long, aes(sample_x, sample_y, fill = correlation)) + geom_tile(color = "white", linewidth = 0.15) +
    scale_fill_gradient(low = "#F7FBFF", high = "#08306B", limits = c(min(corr_long$correlation), 1)) +
    coord_equal() + labs(title = "Sample correlation", subtitle = "Spearman correlation of variance-stabilized miRNA profiles", x = NULL, y = NULL, fill = "rho") +
    theme_report() + theme(axis.text.x = element_text(angle = 55, hjust = 1, size = 8), axis.text.y = element_text(size = 8), legend.position = "right")
  save_plot_all(p_corr, file.path(root, "figures", "qc", "sample_correlation"), width = 10, height = 9)

  design_df <- metadata
  design_df$subject_nested <- factor(design_df$subject_nested, levels = rev(unique(design_df$subject_nested)))
  p_design <- ggplot(design_df, aes(time, subject_nested, group = subject_nested, color = group)) +
    geom_line(linewidth = 0.7, alpha = 0.8) + geom_point(size = 3) + scale_color_manual(values = palette) +
    labs(title = "Longitudinal study design", subtitle = "Lines join measurements from the same animal", x = "Time", y = "Animal (group:subject)", color = "Group") + theme_report()
  save_plot_all(p_design, file.path(root, "figures", "qc", "study_design"), width = 9, height = 6)

  variable <- order(apply(transformed, 1, var), decreasing = TRUE)
  chosen <- rownames(transformed)[head(variable, min(6, length(variable)))]
  trajectory <- as.data.frame(t(transformed[chosen, , drop = FALSE])) |>
    rownames_to_column("sample") |> left_join(metadata, by = "sample") |>
    pivot_longer(all_of(chosen), names_to = "mirna_id", values_to = "vst_expression")
  write_csv_table(trajectory, file.path(root, "tables", "paired_trajectories.csv"))
  p_trajectory <- ggplot(trajectory, aes(time, vst_expression, group = subject_nested, color = group)) +
    geom_line(alpha = 0.7) + geom_point(size = 2) + facet_wrap(~ mirna_id, scales = "free_y", ncol = 3) +
    scale_color_manual(values = palette) + labs(title = "Paired trajectories for the most variable miRNAs", subtitle = "Descriptive visualization; inferential conclusions come from the count model", x = "Time", y = "Variance-stabilized expression", color = "Group") + theme_report()
  save_plot_all(p_trajectory, file.path(root, "figures", "qc", "paired_trajectories"), width = 12, height = 8)
  invisible(list(dds = dds, normalized = normalized, transformed = transformed, library = library))
}

make_agreement_plot <- function(fits, cfg, root = "results") {
  interaction_id <- names(fits)[vapply(fits, function(x) x$contrast$type == "interaction", logical(1))][1]
  direct_id <- names(fits)[vapply(fits, function(x) x$contrast$type == "two_group", logical(1))][1]
  if (is.na(interaction_id) || is.na(direct_id)) return(invisible(NULL))
  merged <- inner_join(
    fits[[interaction_id]]$fit$results |> select(mirna_id, interaction_lfc = shrunken_log2FoldChange, interaction_fdr = padj),
    fits[[direct_id]]$fit$results |> select(mirna_id, direct_lfc = shrunken_log2FoldChange, direct_fdr = padj),
    by = "mirna_id"
  ) |> mutate(highlight = (!is.na(interaction_fdr) & interaction_fdr < cfg$analysis$alpha) | (!is.na(direct_fdr) & direct_fdr < cfg$analysis$alpha))
  write_csv_table(merged, file.path(root, "tables", "interaction_direct_agreement.csv"))
  labels <- merged |> arrange(desc(highlight), pmin(interaction_fdr, direct_fdr, na.rm = TRUE)) |> slice_head(n = cfg$analysis$top_labels)
  p <- ggplot(merged, aes(interaction_lfc, direct_lfc, color = highlight)) +
    geom_hline(yintercept = 0, color = "#AAAAAA") + geom_vline(xintercept = 0, color = "#AAAAAA") +
    geom_point(alpha = 0.7) + geom_text_repel(data = labels, aes(label = mirna_id), size = 3, max.overlaps = Inf) +
    scale_color_manual(values = c(`FALSE` = "#A8A8A8", `TRUE` = "#D55E00"), guide = "none") +
    labs(title = "Longitudinal interaction versus direct endpoint difference", subtitle = "Agreement supports, but does not make, the two estimands equivalent", x = "Interaction shrunken log2FC", y = "Endpoint shrunken log2FC") + theme_report()
  save_plot_all(p, file.path(root, "figures", "comparison", "interaction_vs_endpoint"), width = 8, height = 7)
  invisible(merged)
}

write_results_workbook <- function(fits, path = "results/tables/miRNA_differential_results.xlsx") {
  dir.create(dirname(path), recursive = TRUE, showWarnings = FALSE)
  workbook <- createWorkbook()
  for (id in names(fits)) {
    sheet <- substr(id, 1, 31)
    addWorksheet(workbook, sheet)
    writeDataTable(workbook, sheet, fits[[id]]$fit$results)
    freezePane(workbook, sheet, firstRow = TRUE)
    setColWidths(workbook, sheet, cols = 1:min(15, ncol(fits[[id]]$fit$results)), widths = "auto")
  }
  saveWorkbook(workbook, path, overwrite = TRUE)
  invisible(path)
}

validate_output_completeness <- function(cfg, report_path = NULL, root = "results") {
  required <- c(
    file.path(root, "tables", "sample_inventory.csv"),
    file.path(root, "tables", "sample_qc.csv"),
    file.path(root, "tables", "contrast_summary.csv"),
    file.path(root, "figures", "qc", "study_design.png"),
    file.path(root, "figures", "qc", "library_size.png"),
    file.path(root, "figures", "qc", "pca.png"),
    file.path(root, "figures", "qc", "sample_correlation.png")
  )
  for (contrast in cfg$contrasts) {
    stem <- file.path(root, "figures", "contrasts", contrast$id)
    required <- c(required, file.path(root, "tables", "contrasts", paste0(contrast$id, ".csv")), paste0(stem, c("_ma.png", "_volcano.png", "_forest.png", "_heatmap.png")))
  }
  if (!is.null(report_path)) required <- c(required, report_path)
  missing <- required[!file.exists(required)]
  empty <- required[file.exists(required) & file.info(required)$size <= 0]
  if (length(missing) || length(empty)) {
    stopf("Output completeness check failed. Missing: %s; empty: %s", paste(missing, collapse = ", "), paste(empty, collapse = ", "))
  }
  if (!is.null(report_path) && file.info(report_path)$size < 20000) stopf("Rendered report is unexpectedly small: %s", report_path)
  invisible(TRUE)
}
