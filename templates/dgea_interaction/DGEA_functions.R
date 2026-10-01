suppressPackageStartupMessages({
  library(DESeq2)
  library(tximport)
  library(data.table)
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
  library(clusterProfiler)
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
  required <- c("sample", "include", "genotype", "condition", "subject")
  missing <- setdiff(required, names(metadata))
  if (length(missing)) stopf("Sample metadata is missing: %s", paste(missing, collapse = ", "))
  metadata <- metadata |>
    mutate(include = tolower(include) %in% c("true", "1", "yes", "y")) |>
    filter(include)
  if (!nrow(metadata)) stopf("No samples are enabled in config/samples.csv.")
  if (anyDuplicated(metadata$sample)) stopf("Enabled sample names must be unique.")
  if (any(!complete.cases(metadata[, c("sample", "genotype", "condition", "subject")]))) {
    stopf("Enabled sample metadata contains missing values.")
  }
  metadata$subject_nested <- interaction(metadata$genotype, metadata$subject, drop = TRUE, sep = "_")
  metadata
}

normalize_application <- function(x) tolower(gsub("[^[:alnum:]]", "", x %||% ""))

import_gene_counts <- function(salmon_dir, tx2gene_file, metadata, application = "") {
  if (!file.exists(tx2gene_file)) stopf("tx2gene mapping not found: %s", tx2gene_file)
  tx2gene <- data.table::fread(
    tx2gene_file,
    col.names = c("transcript_id", "gene_id", "gene_name")
  )
  if (ncol(tx2gene) < 3) stopf("tx2gene mapping must contain transcript, gene, and gene-name columns.")
  files <- file.path(salmon_dir, metadata$sample, "quant.sf")
  names(files) <- metadata$sample
  if (any(!file.exists(files))) stopf("Missing quant.sf for: %s", paste(names(files)[!file.exists(files)], collapse = ", "))
  counts_from_abundance <- if (normalize_application(application) == "nfcorernaseq") "lengthScaledTPM" else "no"
  txi <- tximport::tximport(
    files,
    type = "salmon",
    tx2gene = tx2gene[, c("transcript_id", "gene_id")],
    countsFromAbundance = counts_from_abundance
  )
  counts <- round(txi$counts)
  counts <- counts[, metadata$sample, drop = FALSE]
  annotation <- unique(as.data.frame(tx2gene[, c("gene_id", "gene_name")]))
  annotation <- annotation[!duplicated(annotation$gene_id), , drop = FALSE]
  list(counts = counts, txi = txi, annotation = annotation, counts_from_abundance = counts_from_abundance)
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
  theme_minimal(base_size = 15) +
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

categorical_palette <- function(values, preferred = character()) {
  values <- unique(as.character(values[!is.na(values)]))
  output <- stats::setNames(rep(NA_character_, length(values)), values)
  matched <- intersect(values, names(preferred))
  output[matched] <- preferred[matched]
  fallback <- setdiff(c("#0072B2", "#D55E00", "#009E73", "#CC79A7", "#E69F00", "#56B4E9"), unname(output[!is.na(output)]))
  output[is.na(output)] <- rep(fallback, length.out = sum(is.na(output)))
  output
}

wrap_two_lines <- function(x, width = 42) {
  vapply(x, function(label) {
    lines <- strwrap(as.character(label), width = width)
    if (length(lines) <= 2) return(paste(lines, collapse = "\n"))
    paste(lines[[1]], paste(lines[-1], collapse = " "), sep = "\n")
  }, character(1))
}

save_plot_all <- function(plot, stem, width = 12, height = 8) {
  width <- max(width, 12)
  height <- max(height, 8)
  dir.create(dirname(stem), recursive = TRUE, showWarnings = FALSE)
  ggsave(paste0(stem, ".png"), plot, width = width, height = height, dpi = 450, bg = "white")
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
  if (sum(keep) < 2) stopf("Filtering retained fewer than two genes; revise min_count/min_samples.")
  counts[keep, , drop = FALSE]
}

prepare_dds <- function(counts, metadata, design, label) {
  metadata <- as.data.frame(metadata)
  rownames(metadata) <- metadata$sample
  assert_full_rank(design, metadata, label)
  dds <- suppressMessages(DESeqDataSetFromMatrix(countData = counts[, metadata$sample, drop = FALSE], colData = metadata, design = design))
  DESeq(dds, quiet = TRUE)
}

result_frame <- function(res, shrunk, contrast, cfg, annotation = NULL) {
  output <- as.data.frame(res) |>
    rownames_to_column("gene_id") |>
    transmute(
      gene_id,
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
    rownames_to_column("gene_id") |>
    select(gene_id, shrunken_log2FoldChange = log2FoldChange)
  output <- output |>
    left_join(shrink_df, by = "gene_id") |>
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
  if (!is.null(annotation)) {
    output <- output |>
      left_join(as_tibble(annotation), by = "gene_id") |>
      rename(gene_symbol = gene_name) |>
      relocate(gene_symbol, .before = gene_id)
  }
  output
}

fit_contrast <- function(filtered_counts, metadata, contrast, cfg, annotation = NULL) {
  kind <- contrast$type
  if (kind == "interaction") {
    keep <- metadata$genotype %in% c(contrast$base_group, contrast$target_group) &
      metadata$condition %in% c(contrast$base_condition, contrast$target_condition)
    md <- droplevels(metadata[keep, , drop = FALSE])
    md$genotype <- relevel(factor(md$genotype), contrast$base_group)
    md$condition <- relevel(factor(md$condition), contrast$base_condition)
    md$subject_nested <- factor(interaction(md$genotype, md$subject, drop = TRUE, sep = "_"))
    md$genotype_condition_interaction <- as.integer(
      md$genotype == contrast$target_group & md$condition == contrast$target_condition
    )
    design <- ~ subject_nested + condition + genotype_condition_interaction
    dds <- prepare_dds(filtered_counts[, md$sample, drop = FALSE], md, design, contrast$id)
    interaction_names <- resultsNames(dds)[grepl("genotype_condition_interaction", resultsNames(dds), fixed = TRUE)]
    if (length(interaction_names) != 1) {
      stopf("Expected one interaction coefficient for '%s'; found: %s", contrast$id, paste(interaction_names, collapse = ", "))
    }
    res <- results(dds, name = interaction_names[[1]], alpha = cfg$analysis$alpha)
    shrunk <- lfcShrink(dds, coef = interaction_names[[1]], res = res, type = "normal", quiet = TRUE)
    model_formula <- "~ subject_nested + condition + genotype_condition_interaction"
    coefficient <- interaction_names[[1]]
  } else if (kind == "paired_condition") {
    keep <- metadata$genotype == contrast$group & metadata$condition %in% c(contrast$base_condition, contrast$target_condition)
    md <- droplevels(metadata[keep, , drop = FALSE])
    md$condition <- relevel(factor(md$condition), contrast$base_condition)
    md$subject_nested <- factor(md$subject_nested)
    design <- ~ subject_nested + condition
    dds <- prepare_dds(filtered_counts[, md$sample, drop = FALSE], md, design, contrast$id)
    contrast_vector <- c("condition", contrast$target_condition, contrast$base_condition)
    res <- results(dds, contrast = contrast_vector, alpha = cfg$analysis$alpha)
    shrunk <- lfcShrink(dds, contrast = contrast_vector, res = res, type = "normal", quiet = TRUE)
    model_formula <- "~ subject_nested + condition"
    coefficient <- paste(contrast_vector, collapse = ":")
  } else if (kind == "two_group") {
    keep <- metadata$condition == contrast$at_condition & metadata$genotype %in% c(contrast$base_group, contrast$target_group)
    md <- droplevels(metadata[keep, , drop = FALSE])
    md$genotype <- relevel(factor(md$genotype), contrast$base_group)
    design <- ~ genotype
    dds <- prepare_dds(filtered_counts[, md$sample, drop = FALSE], md, design, contrast$id)
    contrast_vector <- c("genotype", contrast$target_group, contrast$base_group)
    res <- results(dds, contrast = contrast_vector, alpha = cfg$analysis$alpha)
    shrunk <- lfcShrink(dds, contrast = contrast_vector, res = res, type = "normal", quiet = TRUE)
    model_formula <- "~ genotype"
    coefficient <- paste(contrast_vector, collapse = ":")
  } else {
    stopf("Unsupported contrast type: %s", kind)
  }
  list(
    dds = dds,
    metadata = md,
    results = result_frame(res, shrunk, contrast, cfg, annotation),
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
  plot_df <- results |>
    filter(baseMean > 0, !is.na(shrunken_log2FoldChange))
  labels <- plot_df |>
    filter(evidence_threshold, !is.na(padj)) |>
    arrange(padj, desc(abs(shrunken_log2FoldChange))) |>
    slice_head(n = cfg$analysis$top_labels) |>
    mutate(display_label = ifelse(is.na(gene_symbol) | gene_symbol == "", gene_id, gene_symbol))
  ggplot(plot_df, aes(baseMean, shrunken_log2FoldChange, color = evidence_threshold)) +
    geom_point(alpha = 0.65, size = 1.8) +
    geom_hline(yintercept = c(-1, 1) * cfg$analysis$lfc_threshold, linetype = 2, color = "#666666") +
    geom_text_repel(
      data = labels,
      aes(label = display_label),
      color = "#7A2E00",
      size = 3.2,
      box.padding = 0.5,
      point.padding = 0.25,
      min.segment.length = 0,
      max.overlaps = Inf,
      seed = 1,
      show.legend = FALSE
    ) +
    scale_x_log10(labels = label_number()) +
    scale_color_manual(values = c(`FALSE` = "#A8A8A8", `TRUE` = "#D55E00"), guide = "none") +
    labs(
      title = "MA plot",
      subtitle = contrast$label,
      caption = if (nrow(labels)) sprintf("Top %d significant genes by FDR are labeled.", nrow(labels)) else "No genes met the configured significance thresholds.",
      x = "Mean normalized count",
      y = "Shrunken log2 fold change"
    ) +
    theme_report()
}

plot_volcano <- function(results, contrast, cfg) {
  plot_df <- results |> filter(!is.na(padj), !is.na(shrunken_log2FoldChange)) |> mutate(minus_log10_fdr = -log10(pmax(padj, .Machine$double.xmin)))
  labels <- select_labels(plot_df, cfg$analysis$top_labels) |>
    mutate(display_label = ifelse(is.na(gene_symbol) | gene_symbol == "", gene_id, gene_symbol))
  ggplot(plot_df, aes(shrunken_log2FoldChange, minus_log10_fdr, color = evidence_threshold)) +
    geom_point(alpha = 0.68, size = 1.9) +
    geom_vline(xintercept = c(-1, 1) * cfg$analysis$lfc_threshold, linetype = 2, color = "#666666") +
    geom_hline(yintercept = -log10(cfg$analysis$alpha), linetype = 2, color = "#666666") +
    geom_text_repel(data = labels, aes(label = display_label), size = 3, max.overlaps = Inf, box.padding = 0.4) +
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
    mutate(display_label = ifelse(is.na(gene_symbol) | gene_symbol == "", gene_id, gene_symbol),
           display_label = factor(make.unique(display_label), levels = make.unique(display_label)))
  ggplot(top, aes(log2FoldChange, display_label, color = evidence_threshold)) +
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
    pull(gene_id)
  normalized <- log2(counts(dds, normalized = TRUE)[chosen, , drop = FALSE] + 1)
  z <- t(scale(t(normalized)))
  z[!is.finite(z)] <- 0
  md <- as.data.frame(colData(dds))
  label_map <- results |>
    filter(gene_id %in% chosen) |>
    transmute(gene_id, gene_label = ifelse(is.na(gene_symbol) | gene_symbol == "", gene_id, gene_symbol))
  gene_labels <- label_map$gene_label[match(chosen, label_map$gene_id)]
  rownames(z) <- chosen
  sample_keys <- colnames(z)
  annotation_col <- md[sample_keys, c("genotype", "condition"), drop = FALSE]
  colnames(annotation_col) <- c("Genotype", "Condition")
  labels_col <- as.character(md[sample_keys, "sample"])
  annotation_colors <- list(
    Genotype = categorical_palette(
      annotation_col$Genotype,
      c(WT = "#0072B2", TTN = "#D55E00")
    ),
    Condition = categorical_palette(
      annotation_col$Condition,
      c(Control = "#B8B8B8", SinusRhythm = "#009E73", AtrialFibrillation = "#CC79A7")
    )
  )
  heatmap <- pheatmap::pheatmap(
    z,
    color = grDevices::colorRampPalette(c("#2166AC", "#F7F7F7", "#B2182B"))(101),
    breaks = seq(-3, 3, length.out = 102),
    cluster_rows = FALSE,
    cluster_cols = TRUE,
    clustering_distance_cols = "correlation",
    clustering_method = "complete",
    treeheight_row = 0,
    treeheight_col = 45,
    annotation_col = annotation_col,
    annotation_colors = annotation_colors,
    annotation_names_col = TRUE,
    labels_col = labels_col,
    labels_row = gene_labels,
    angle_col = 45,
    border_color = NA,
    legend = TRUE,
    legend_breaks = c(-3, 0, 3),
    legend_labels = c("-3", "0", "3"),
    fontsize = 11,
    fontsize_row = 10,
    fontsize_col = 10,
    main = "",
    silent = TRUE
  )
  heatmap$gtable
}

write_contrast_outputs <- function(fit, contrast, cfg, root = "results") {
  table_path <- file.path(root, "tables", "comparisons", paste0(contrast$id, ".xlsx"))
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

make_qc_outputs <- function(counts, metadata, cfg, annotation = NULL, root = "results") {
  dds <- suppressMessages(DESeqDataSetFromMatrix(countData = counts, colData = data.frame(row.names = metadata$sample), design = ~ 1))
  dds <- estimateSizeFactors(dds)
  normalized <- counts(dds, normalized = TRUE)
  vsd <- varianceStabilizingTransformation(dds, blind = TRUE)
  transformed <- assay(vsd)
  library <- tibble(
    sample = colnames(counts),
    library_size = colSums(counts),
    detected_genes = colSums(counts > 0)
  ) |> left_join(metadata, by = "sample")
  write_csv_table(library, file.path(root, "tables", "sample_qc.csv"))
  write_csv_table(as.data.frame(normalized) |> rownames_to_column("gene_id"), file.path(root, "tables", "normalized_counts.csv"))

  palette <- group_palette(unique(metadata$genotype))
  p_library <- ggplot(library, aes(reorder(sample, library_size), library_size, fill = genotype)) +
    geom_col(width = 0.75) + coord_flip() + scale_fill_manual(values = palette) +
    scale_y_continuous(labels = label_number()) +
    labs(title = "Raw library size", subtitle = "Total gene-level counts before normalization", x = NULL, y = "Counts", fill = "Genotype") + theme_report()
  save_plot_all(p_library, file.path(root, "figures", "qc", "library_size"), width = 9, height = 6.5)

  p_detected <- ggplot(library, aes(reorder(sample, detected_genes), detected_genes, fill = genotype)) +
    geom_col(width = 0.75) + coord_flip() + scale_fill_manual(values = palette) +
    labs(title = "Detected genes", subtitle = "Number with at least one raw count", x = NULL, y = "Detected genes", fill = "Genotype") + theme_report()
  save_plot_all(p_detected, file.path(root, "figures", "qc", "detected_genes"), width = 9, height = 6.5)

  pca <- prcomp(t(transformed))
  percent <- 100 * pca$sdev^2 / sum(pca$sdev^2)
  pca_df <- as.data.frame(pca$x[, 1:2, drop = FALSE]) |> rownames_to_column("sample") |> left_join(metadata, by = "sample")
  write_csv_table(pca_df, file.path(root, "tables", "pca_coordinates.csv"))
  p_pca <- ggplot(pca_df, aes(PC1, PC2, color = genotype, shape = condition, label = sample)) +
    geom_point(size = 3.2) + geom_text_repel(size = 3, max.overlaps = Inf) + scale_color_manual(values = palette) +
    labs(title = "PCA of variance-stabilized counts", subtitle = "No confidence ellipse is shown because the study is small", x = sprintf("PC1 (%.1f%%)", percent[1]), y = sprintf("PC2 (%.1f%%)", percent[2]), color = "Genotype", shape = "Condition") + theme_report()
  save_plot_all(p_pca, file.path(root, "figures", "qc", "pca"), width = 9, height = 7)

  correlations <- cor(transformed, method = "spearman")
  corr_long <- as.data.frame(correlations) |> rownames_to_column("sample_x") |> pivot_longer(-sample_x, names_to = "sample_y", values_to = "correlation")
  write_csv_table(corr_long, file.path(root, "tables", "sample_correlations.csv"))
  p_corr <- ggplot(corr_long, aes(sample_x, sample_y, fill = correlation)) + geom_tile(color = "white", linewidth = 0.15) +
    scale_fill_gradient(low = "#F7FBFF", high = "#08306B", limits = c(min(corr_long$correlation), 1)) +
    coord_equal() + labs(title = "Sample correlation", subtitle = "Spearman correlation of variance-stabilized gene profiles", x = NULL, y = NULL, fill = "rho") +
    theme_report() + theme(axis.text.x = element_text(angle = 55, hjust = 1, size = 8), axis.text.y = element_text(size = 8), legend.position = "right")
  save_plot_all(p_corr, file.path(root, "figures", "qc", "sample_correlation"), width = 10, height = 9)

  design_df <- metadata
  design_df$subject_nested <- factor(design_df$subject_nested, levels = rev(unique(design_df$subject_nested)))
  p_design <- ggplot(design_df, aes(condition, subject_nested, group = subject_nested, color = genotype)) +
    geom_line(linewidth = 0.7, alpha = 0.8) + geom_point(size = 3) + scale_color_manual(values = palette) +
    labs(title = "Paired stimulation design", subtitle = "Lines join measurements from the same individual", x = "Condition", y = "Individual (genotype:subject)", color = "Genotype") + theme_report()
  save_plot_all(p_design, file.path(root, "figures", "qc", "study_design"), width = 9, height = 6)

  variable <- order(apply(transformed, 1, var), decreasing = TRUE)
  chosen <- rownames(transformed)[head(variable, min(6, length(variable)))]
  trajectory <- as.data.frame(t(transformed[chosen, , drop = FALSE])) |>
    rownames_to_column("sample") |> left_join(metadata, by = "sample") |>
    pivot_longer(all_of(chosen), names_to = "gene_id", values_to = "vst_expression")
  if (!is.null(annotation)) {
    trajectory <- trajectory |>
      left_join(as_tibble(annotation), by = "gene_id") |>
      mutate(gene_symbol = ifelse(is.na(gene_name) | gene_name == "", gene_id, gene_name))
  } else {
    trajectory$gene_symbol <- trajectory$gene_id
  }
  write_csv_table(trajectory, file.path(root, "tables", "paired_trajectories.csv"))
  p_trajectory <- ggplot(trajectory, aes(condition, vst_expression, group = subject_nested, color = genotype)) +
    geom_line(alpha = 0.7) + geom_point(size = 2) + facet_wrap(~ gene_symbol, scales = "free_y", ncol = 3) +
    scale_color_manual(values = palette) + labs(title = "Paired trajectories for the most variable genes", subtitle = "Descriptive visualization; inferential conclusions come from the count model", x = "Condition", y = "Variance-stabilized expression", color = "Genotype") + theme_report()
  save_plot_all(p_trajectory, file.path(root, "figures", "qc", "paired_trajectories"), width = 12, height = 8)
  invisible(list(dds = dds, normalized = normalized, transformed = transformed, library = library))
}

classify_response <- function(fits, interaction_id, reference_id, target_id, cfg, root = "results") {
  required <- c(interaction_id, reference_id, target_id)
  if (!all(required %in% names(fits))) stopf("Response classification is missing fitted contrasts: %s", paste(setdiff(required, names(fits)), collapse = ", "))
  merged <- inner_join(
    fits[[interaction_id]]$fit$results |> select(gene_id, gene_symbol, interaction_lfc = shrunken_log2FoldChange, interaction_fdr = padj),
    fits[[reference_id]]$fit$results |> select(gene_id, reference_lfc = shrunken_log2FoldChange, reference_fdr = padj),
    by = "gene_id"
  ) |>
    inner_join(fits[[target_id]]$fit$results |> select(gene_id, target_lfc = shrunken_log2FoldChange, target_fdr = padj), by = "gene_id") |>
    mutate(
      interaction_significant = !is.na(interaction_fdr) & interaction_fdr < cfg$analysis$alpha,
      reference_significant = !is.na(reference_fdr) & reference_fdr < cfg$analysis$alpha,
      target_significant = !is.na(target_fdr) & target_fdr < cfg$analysis$alpha,
      response_class = case_when(
        !interaction_significant ~ "not_interaction_significant",
        sign(reference_lfc) != 0 & sign(target_lfc) != 0 & sign(reference_lfc) != sign(target_lfc) ~ "opposite_response",
        target_significant & !reference_significant ~ "target_specific_response",
        !target_significant & reference_significant ~ "lost_or_blunted_response",
        abs(target_lfc) > abs(reference_lfc) ~ "enhanced_response",
        abs(target_lfc) < abs(reference_lfc) ~ "reduced_response",
        TRUE ~ "other_interaction"
      )
    )
  summary <- merged |> count(response_class, name = "n_genes") |> mutate(interaction_id = interaction_id, .before = 1)
  labels <- merged |> filter(interaction_significant) |> arrange(interaction_fdr) |> slice_head(n = cfg$analysis$top_labels) |>
    mutate(display_label = ifelse(is.na(gene_symbol) | gene_symbol == "", gene_id, gene_symbol))
  p <- ggplot(merged, aes(reference_lfc, target_lfc, color = response_class)) +
    geom_hline(yintercept = 0, color = "#AAAAAA") + geom_vline(xintercept = 0, color = "#AAAAAA") +
    geom_abline(slope = 1, intercept = 0, linetype = 2, color = "#777777") +
    geom_point(alpha = 0.65, size = 1.8) + geom_text_repel(data = labels, aes(label = display_label), size = 3, max.overlaps = Inf) +
    scale_color_manual(values = c(not_interaction_significant = "#BDBDBD", opposite_response = "#CC79A7", target_specific_response = "#D55E00", lost_or_blunted_response = "#56B4E9", enhanced_response = "#E69F00", reduced_response = "#0072B2", other_interaction = "#009E73")) +
    labs(title = fits[[interaction_id]]$contrast$label, subtitle = "Within-genotype responses; colors are assigned only after the interaction test", x = paste(reference_id, "shrunken log2FC"), y = paste(target_id, "shrunken log2FC"), color = "Response class") + theme_report()
  save_plot_all(p, file.path(root, "figures", "response_classes", interaction_id), width = 9, height = 7)
  list(summary = summary, details = merged)
}

organism_db <- function(organism) {
  key <- normalize_application(organism)
  packages <- c(hsapiens = "org.Hs.eg.db", mmusculus = "org.Mm.eg.db", rnorvegicus = "org.Rn.eg.db", sscrofa = "org.Ss.eg.db")
  package <- unname(packages[[key]])
  if (is.null(package) || !requireNamespace(package, quietly = TRUE)) return(NULL)
  get(package, envir = asNamespace(package))
}

run_pathway_analysis <- function(fits, organism, cfg, root = "results") {
  status <- list()
  tables <- list()
  if (!isTRUE(cfg$analysis$pathway_analysis)) {
    write_csv_table(tibble(status = "disabled", detail = "Pathway analysis disabled in config."), file.path(root, "tables", "pathways", "status.csv"))
    return(list(status = tibble(status = "disabled", detail = "Pathway analysis disabled in config."), tables = tables))
  }
  orgdb <- organism_db(organism)
  if (is.null(orgdb)) {
    write_csv_table(tibble(status = "unavailable", detail = paste("No installed OrgDb mapping for", organism)), file.path(root, "tables", "pathways", "status.csv"))
    return(list(status = tibble(status = "unavailable", detail = paste("No installed OrgDb mapping for", organism)), tables = tables))
  }
  if (requireNamespace("BiocParallel", quietly = TRUE)) {
    BiocParallel::register(BiocParallel::SerialParam(), default = TRUE)
  }
  for (id in names(fits)) {
    result <- fits[[id]]$fit$results |> mutate(ensembl = sub("\\..*$", "", gene_id))
    mapping <- suppressMessages(clusterProfiler::bitr(unique(result$ensembl), fromType = "ENSEMBL", toType = "ENTREZID", OrgDb = orgdb))
    ranked <- result |> inner_join(mapping, by = c("ensembl" = "ENSEMBL")) |> filter(!is.na(stat)) |> group_by(ENTREZID) |> slice_max(abs(stat), n = 1, with_ties = FALSE) |> ungroup()
    gene_list <- ranked$stat
    names(gene_list) <- ranked$ENTREZID
    gene_list <- sort(gene_list, decreasing = TRUE)
    gsea <- if (length(gene_list) >= 20) suppressWarnings(tryCatch(clusterProfiler::gseGO(geneList = gene_list, OrgDb = orgdb, ont = "BP", keyType = "ENTREZID", pAdjustMethod = "BH", pvalueCutoff = 1, verbose = FALSE), error = function(e) NULL)) else NULL
    empty_gsea_table <- tibble(
      ID = character(), Description = character(), setSize = integer(),
      enrichmentScore = double(), NES = double(), pvalue = double(),
      p.adjust = double(), qvalue = double(), rank = integer(),
      leading_edge = character(), core_enrichment = character()
    )
    table <- if (is.null(gsea)) empty_gsea_table else as_tibble(as.data.frame(gsea))
    if (!ncol(table)) table <- empty_gsea_table
    tables[[id]] <- table
    pathway_stem <- file.path(root, "figures", "pathways", paste0(id, "_gsea_go_bp"))
    if (nrow(table)) {
      top <- table |>
        arrange(p.adjust) |>
        slice_head(n = 20) |>
        mutate(
          description_wrapped = wrap_two_lines(Description, width = 42),
          description_wrapped = factor(description_wrapped, levels = rev(unique(description_wrapped))),
          fdr_for_plot = pmax(p.adjust, .Machine$double.xmin)
        )
      p <- ggplot(top, aes(NES, description_wrapped, color = fdr_for_plot, size = setSize)) +
        geom_vline(xintercept = 0, color = "#6B7280", linewidth = 0.4) +
        geom_point(alpha = 0.9) +
        scale_color_viridis_c(
          option = "C",
          direction = -1,
          trans = "log10",
          breaks = scales::log_breaks(n = 4),
          labels = scales::label_scientific(digits = 1),
          guide = guide_colorbar(order = 2, title.position = "top", barheight = grid::unit(45, "mm"), barwidth = grid::unit(5, "mm"))
        ) +
        scale_size_continuous(
          range = c(2.5, 8),
          guide = guide_legend(order = 1, title.position = "top")
        ) +
        labs(
          title = "GO biological-process GSEA",
          subtitle = fits[[id]]$contrast$label,
          x = "Normalized enrichment score",
          y = NULL,
          color = "FDR",
          size = "Gene-set size"
        ) +
        theme_report() +
        theme(
          legend.position = "right",
          legend.box = "vertical",
          axis.text.y = element_text(size = 10.5, lineheight = 0.95),
          plot.subtitle = element_text(size = 12, color = "#4A4A4A")
        )
      pathway_height <- max(8, 3 + 0.32 * sum(lengths(strsplit(as.character(top$description_wrapped), "\n", fixed = TRUE))))
      save_plot_all(p, pathway_stem, width = 12, height = pathway_height)
    } else {
      unlink(paste0(pathway_stem, c(".png", ".pdf", ".svg")))
    }
    status[[id]] <- tibble(contrast_id = id, mapped_genes = length(gene_list), pathways_tested = nrow(table), pathways_fdr = if (nrow(table)) sum(table$p.adjust < cfg$analysis$pathway_padj, na.rm = TRUE) else 0)
  }
  status_table <- bind_rows(status)
  write_csv_table(status_table, file.path(root, "tables", "pathways", "status.csv"))
  list(status = status_table, tables = tables)
}

write_comparison_workbooks <- function(fits, pathway_results, response_details, cfg, root = "results") {
  output_dir <- file.path(root, "tables", "comparisons")
  dir.create(output_dir, recursive = TRUE, showWarnings = FALSE)
  for (id in names(fits)) {
    result <- fits[[id]]$fit$results
    sheets <- list(
      statistics = result,
      fdr_significant = result |> filter(fdr_significant),
      effect_threshold = result |> filter(evidence_threshold)
    )
    pathway <- pathway_results$tables[[id]]
    if (!is.null(pathway)) sheets$GO_BP_GSEA <- pathway |> arrange(p.adjust)
    if (!is.null(response_details[[id]])) sheets$response_classification <- response_details[[id]]
    path <- file.path(output_dir, paste0(id, ".xlsx"))
    workbook <- createWorkbook()
    for (sheet_name in names(sheets)) {
      sheet_data <- as.data.frame(sheets[[sheet_name]])
      addWorksheet(workbook, sheet_name)
      if (nrow(sheet_data)) {
        writeDataTable(workbook, sheet_name, sheet_data)
      } else {
        writeData(workbook, sheet_name, sheet_data, colNames = TRUE)
      }
      freezePane(workbook, sheet_name, firstRow = TRUE)
      setColWidths(workbook, sheet_name, cols = seq_len(ncol(sheet_data)), widths = "auto")
    }
    saveWorkbook(workbook, path, overwrite = TRUE)
  }
  invisible(output_dir)
}

write_interpretation_payload <- function(fits, contrast_summary, response_summary, pathway_results, path) {
  leading <- lapply(fits, function(item) head(item$fit$results, 12))
  payload <- list(
    contrast_summary = contrast_summary,
    response_classes = response_summary,
    pathway_status = pathway_results$status,
    leading_genes = leading
  )
  writeLines(jsonlite::toJSON(payload, dataframe = "rows", auto_unbox = TRUE, na = "null", pretty = TRUE), path)
  invisible(path)
}

write_results_workbook <- function(fits, path = "results/tables/gene_differential_results.xlsx") {
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
    required <- c(required, file.path(root, "tables", "comparisons", paste0(contrast$id, ".xlsx")), paste0(stem, c("_ma.png", "_volcano.png", "_forest.png", "_heatmap.png")))
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
