suppressPackageStartupMessages({
  library(RcppTOML)
  library(readr)
  library(dplyr)
  library(tibble)
  library(stringr)
  library(ggplot2)
  library(tidyr)
})

`%||%` <- function(x, y) if (is.null(x)) y else x

log_info <- function(...) cat(sprintf("[INFO] %s\n", paste(..., collapse = " ")))
log_warn <- function(...) warning(paste(..., collapse = " "), call. = FALSE)
log_error <- function(...) stop(paste(..., collapse = " "), call. = FALSE)

ensure_dirs <- function(root = ".") {
  dirs <- c("results/rds", "results/tables", "results/figures", "results/logs", "reports")
  for (d in dirs) dir.create(file.path(root, d), recursive = TRUE, showWarnings = FALSE)
  invisible(TRUE)
}

coalesce_chr <- function(x, default = "") {
  if (is.null(x) || length(x) == 0 || is.na(x)) return(default)
  as.character(x[[1]])
}

parse_bool <- function(x, default = TRUE) {
  if (is.null(x) || length(x) == 0 || is.na(x)) return(default)
  if (is.logical(x)) return(isTRUE(x))
  v <- tolower(trimws(as.character(x[[1]])))
  if (v %in% c("true", "t", "1", "yes", "y")) return(TRUE)
  if (v %in% c("false", "f", "0", "no", "n")) return(FALSE)
  default
}

parse_bool_vec <- function(x, default = TRUE) {
  vapply(x, parse_bool, logical(1), default = default)
}

config_chr_vector <- function(x) {
  if (is.null(x) || length(x) == 0) return(character(0))
  out <- trimws(as.character(unlist(x, use.names = FALSE)))
  unique(out[nzchar(out)])
}

resolve_path <- function(path) {
  if (length(path) != 1) {
    return(vapply(path, resolve_path, character(1), USE.NAMES = FALSE))
  }
  if (is.null(path) || !nzchar(trimws(as.character(path)))) return(path)
  if (file.exists(path)) return(path)
  alt <- file.path("..", path)
  if (file.exists(alt)) return(alt)
  path
}

save_rds <- function(object, path) {
  dir.create(dirname(path), recursive = TRUE, showWarnings = FALSE)
  saveRDS(object, path)
  invisible(path)
}

read_rds <- function(path) {
  if (!file.exists(path)) log_error("Required artifact missing:", path)
  readRDS(path)
}

write_table <- function(df, path) {
  dir.create(dirname(path), recursive = TRUE, showWarnings = FALSE)
  readr::write_csv(as_tibble(df), path)
  invisible(path)
}

save_plot <- function(plot_obj, path, width = 8, height = 5) {
  dir.create(dirname(path), recursive = TRUE, showWarnings = FALSE)
  ggplot2::ggsave(filename = path, plot = plot_obj, width = width, height = height, units = "in", dpi = 320, bg = "white")
  invisible(path)
}

save_widget <- function(widget, path) {
  dir.create(dirname(path), recursive = TRUE, showWarnings = FALSE)
  htmlwidgets::saveWidget(widget, file = path, selfcontained = TRUE)
  invisible(path)
}

quarto_render_cli <- function(input, output_dir = "reports", output_file = NULL, execute_params = NULL, metadata = NULL) {
  quarto_bin <- Sys.which("quarto")
  if (!nzchar(quarto_bin)) log_error("Quarto CLI not found on PATH")
  dir.create(output_dir, recursive = TRUE, showWarnings = FALSE)
  args <- c("render", input, "--output-dir", output_dir, "--no-clean")
  if (!is.null(output_file) && nzchar(output_file)) {
    args <- c(args, "--output", output_file)
  }
  metadata_file <- NULL
  if (!is.null(metadata) && length(metadata) > 0) {
    metadata_clean <- Filter(
      Negate(is.null),
      lapply(metadata, function(value) {
        value_chr <- trimws(as.character(value[[1]]))
        if (!nzchar(value_chr)) return(NULL)
        value_chr
      })
    )
    if (length(metadata_clean) > 0) {
      metadata_file <- tempfile(pattern = "quarto-metadata-", fileext = ".yml")
      yaml::write_yaml(metadata_clean, metadata_file)
      args <- c(args, "--metadata-file", metadata_file)
    }
  }
  params_file <- NULL
  if (!is.null(execute_params) && length(execute_params) > 0) {
    params_file <- tempfile(pattern = "quarto-params-", fileext = ".yml")
    yaml::write_yaml(execute_params, params_file)
    args <- c(args, "--execute-params", params_file)
  }
  on.exit({
    if (!is.null(metadata_file) && file.exists(metadata_file)) unlink(metadata_file)
    if (!is.null(params_file) && file.exists(params_file)) unlink(params_file)
  }, add = TRUE)
  status <- system2(quarto_bin, args = args)
  if (!identical(status, 0L)) {
    log_error("Quarto render failed for", input, "with exit code", status)
  }
  invisible(file.path(output_dir, output_file %||% input))
}

load_project_config <- function(path = "config/datasets.toml") {
  if (!file.exists(path)) log_error("Config not found:", path)
  RcppTOML::parseTOML(path)
}

load_samples <- function(path = "config/samples.csv") {
  if (!file.exists(path)) log_error("Sample sheet not found:", path)
  readr::read_csv(path, show_col_types = FALSE)
}

load_comparisons <- function(path = "config/comparisons.csv") {
  if (!file.exists(path)) log_error("Comparisons file not found:", path)
  df <- readr::read_csv(path, show_col_types = FALSE)
  required <- c("comparison_id", "target_group", "base_group")
  missing <- setdiff(required, names(df))
  if (length(missing) > 0) log_error("comparisons.csv missing required columns:", paste(missing, collapse = ", "))
  if (!("enabled" %in% names(df))) df$enabled <- TRUE
  if (!("name" %in% names(df))) df$name <- df$comparison_id
  if (!("sample_filter" %in% names(df))) df$sample_filter <- ""
  if (!("covariates" %in% names(df))) df$covariates <- ""
  if (!("alpha" %in% names(df))) df$alpha <- NA_real_
  if (!("delta_beta_min" %in% names(df))) df$delta_beta_min <- NA_real_
  df
}

normalize_array_type <- function(array_type) {
  at <- toupper(trimws(as.character(array_type)))
  dplyr::case_when(
    at %in% c("450K", "HM450", "HUMANMETHYLATION450", "HUMANMETHYLATION450K") ~ "450K",
    at %in% c("EPIC", "850K", "EPIC850K") ~ "EPIC",
    at %in% c("EPIC_V2", "EPICV2", "ILLUMINAHUMANMETHYLATIONEPICV2") ~ "EPIC_V2",
    at %in% c("AUTO", "MIXED", "") ~ "AUTO",
    TRUE ~ at
  )
}

normalize_array_type_for_dmr <- function(array_types) {
  types <- unique(na.omit(vapply(array_types, normalize_array_type, character(1))))
  types <- setdiff(types, "AUTO")
  if (length(types) == 0) return("EPICv1")
  if (length(types) == 1 && identical(types, "EPIC_V2")) return("EPICv2")
  if ("450K" %in% types) return("450K")
  "EPICv1"
}

normalize_array_type_for_gometh <- function(array_types) {
  types <- unique(na.omit(vapply(array_types, normalize_array_type, character(1))))
  types <- setdiff(types, "AUTO")
  if (length(types) == 0) return("EPIC")
  if ("450K" %in% types) return("450K")
  "EPIC"
}

has_epicv2_probe_suffix <- function(probe_ids) {
  if (is.null(probe_ids) || length(probe_ids) == 0) return(FALSE)
  any(grepl("_[A-Za-z]+[0-9]+$", as.character(probe_ids)))
}

resolve_dmrcate_array_type <- function(probe_ids, configured_type = "EPICv1") {
  if (has_epicv2_probe_suffix(probe_ids)) return("EPICv2")
  at <- normalize_array_type(configured_type)
  if (identical(at, "450K")) return("450K")
  "EPICv1"
}

resolve_gometh_array_type <- function(probe_ids, configured_type = "EPIC") {
  at <- normalize_array_type(configured_type)
  if (identical(at, "450K")) return("450K")
  "EPIC"
}

annotation_package_for_array_type <- function(array_type, tool = c("dmr", "gometh")) {
  tool <- match.arg(tool)
  if (tool == "gometh") {
    if (identical(array_type, "450K")) return("IlluminaHumanMethylation450kanno.ilmn12.hg19")
    return("IlluminaHumanMethylationEPICanno.ilm10b4.hg19")
  }
  if (identical(array_type, "450K")) return("IlluminaHumanMethylation450kanno.ilmn12.hg19")
  if (identical(array_type, "EPICv2")) return("IlluminaHumanMethylationEPICv2anno.20a1.hg38")
  "IlluminaHumanMethylationEPICanno.ilm10b4.hg19"
}

ensure_annotation_package_loaded <- function(array_type, tool = c("dmr", "gometh")) {
  tool <- match.arg(tool)
  pkg <- annotation_package_for_array_type(array_type, tool = tool)
  ok <- suppressPackageStartupMessages(require(pkg, character.only = TRUE, quietly = TRUE))
  if (!ok) log_warn("Required annotation package not available for", tool, ":", pkg)
  invisible(ok)
}

datasets_to_tibble <- function(cfg) {
  raw <- cfg$datasets
  if (is.null(raw) || length(raw) == 0) return(tibble::tibble())
  rows <- lapply(raw, function(entry) {
    tibble::tibble(
      dataset_id = coalesce_chr(entry$dataset_id, ""),
      source = coalesce_chr(entry$source, ""),
      path = coalesce_chr(entry$path, ""),
      accession = coalesce_chr(entry$accession, ""),
      array_type = normalize_array_type(coalesce_chr(entry$array_type, coalesce_chr(cfg$project$array_type, "AUTO"))),
      enabled = parse_bool(entry$enabled, default = TRUE)
    )
  })
  dplyr::bind_rows(rows)
}

validate_workspace <- function(cfg, samples, comparisons = NULL) {
  for (section in c("project", "processing", "filter", "batch_correction", "dmr", "enrichment", "drilldown")) {
    if (is.null(cfg[[section]])) log_error("Missing config section [", section, "]")
  }
  datasets <- datasets_to_tibble(cfg) %>% dplyr::filter(.data$enabled)
  if (nrow(datasets) == 0) log_error("No datasets configured in config/datasets.toml")
  resolved_paths <- resolve_path(datasets$path)
  missing_paths <- datasets$path[!file.exists(resolved_paths)]
  if (length(missing_paths) > 0) {
    log_warn("Some dataset paths do not exist yet:", paste(unique(missing_paths), collapse = ", "))
  }
  required_sample_cols <- c("sample_id", "dataset_id", "group", "include")
  missing_sample_cols <- setdiff(required_sample_cols, names(samples))
  if (length(missing_sample_cols) > 0) {
    log_error("samples.csv missing required columns:", paste(missing_sample_cols, collapse = ", "))
  }
  dup_ids <- samples$sample_id[duplicated(samples$sample_id)]
  if (length(dup_ids) > 0) log_error("Duplicate sample_id values:", paste(unique(dup_ids), collapse = ", "))
  if (!is.null(comparisons) && is.data.frame(comparisons)) {
    required_cmp_cols <- c("comparison_id", "target_group", "base_group")
    missing_cmp_cols <- setdiff(required_cmp_cols, names(comparisons))
    if (length(missing_cmp_cols) > 0) {
      log_error("comparison data frame missing required columns:", paste(missing_cmp_cols, collapse = ", "))
    }
  }
  invisible(TRUE)
}

configure_rgset_annotation <- function(rgset, array_type, genome_build) {
  at <- normalize_array_type(array_type)
  if (identical(at, "EPIC_V2")) {
    annotation(rgset)["array"] <- "IlluminaHumanMethylationEPICv2"
    annotation(rgset)["annotation"] <- if (tolower(genome_build) == "hg38") "20a1.hg38" else "20a1.hg38"
  }
  rgset
}

resolve_sample_basenames <- function(samples, dataset_path) {
  out <- tibble::as_tibble(samples)
  default_dir <- resolve_path(dataset_path)
  from_pair <- rep(NA_character_, nrow(out))
  if (all(c("SentrixBarcode", "SentrixPosition") %in% names(out))) {
    valid_pair <- !is.na(out$SentrixBarcode) & !is.na(out$SentrixPosition) &
      trimws(as.character(out$SentrixBarcode)) != "" & trimws(as.character(out$SentrixPosition)) != ""
    sample_dirs <- if ("idat_dir" %in% names(out)) ifelse(is.na(out$idat_dir) | trimws(out$idat_dir) == "", default_dir, out$idat_dir) else rep(default_dir, nrow(out))
    from_pair[valid_pair] <- file.path(sample_dirs[valid_pair], paste0(out$SentrixBarcode[valid_pair], "_", out$SentrixPosition[valid_pair]))
  }
  from_override <- rep(NA_character_, nrow(out))
  if ("idat_basename" %in% names(out)) {
    override <- as.character(out$idat_basename)
    override[is.na(override) | trimws(override) == ""] <- NA_character_
    rel_idx <- which(!is.na(override) & !startsWith(override, "/"))
    if (length(rel_idx) > 0) {
      sample_dirs <- if ("idat_dir" %in% names(out)) ifelse(is.na(out$idat_dir) | trimws(out$idat_dir) == "", default_dir, out$idat_dir) else rep(default_dir, nrow(out))
      override[rel_idx] <- file.path(sample_dirs[rel_idx], override[rel_idx])
    }
    from_override <- override
  }
  out$Basename <- dplyr::coalesce(from_override, from_pair)
  if (any(is.na(out$Basename) | trimws(out$Basename) == "")) {
    bad <- out$sample_id[is.na(out$Basename) | trimws(out$Basename) == ""]
    log_error("Could not resolve IDAT basenames for sample_id:", paste(bad, collapse = ", "))
  }
  out
}

locate_idat_file <- function(basename, channel = c("Red", "Grn")) {
  channel <- match.arg(channel)
  candidates <- c(
    paste0(basename, "_", channel, ".idat"),
    paste0(basename, "_", channel, ".idat.gz")
  )
  hit <- candidates[file.exists(candidates)][1]
  if (is.na(hit) || !nzchar(hit)) {
    log_error("Unable to locate", channel, "IDAT for basename:", basename)
  }
  hit
}

guess_array_info_from_nprobes <- function(n_probes) {
  if (is.na(n_probes)) {
    return(list(array_label = "Unknown", array_type = "AUTO"))
  }
  if (n_probes >= 622000 && n_probes <= 623000) {
    return(list(array_label = "IlluminaHumanMethylation450k", array_type = "450K"))
  }
  if (n_probes >= 1050000 && n_probes <= 1053000) {
    return(list(array_label = "IlluminaHumanMethylationEPIC", array_type = "EPIC"))
  }
  if (n_probes >= 1032000 && n_probes <= 1033000) {
    return(list(array_label = "IlluminaHumanMethylationEPIC", array_type = "EPIC"))
  }
  if (n_probes >= 1105000 && n_probes <= 1105300) {
    return(list(array_label = "IlluminaHumanMethylationEPICv2", array_type = "EPIC_V2"))
  }
  list(array_label = "Unknown", array_type = "AUTO")
}

infer_target_import_groups <- function(targets, configured_array_type = "AUTO") {
  configured_array_type <- normalize_array_type(configured_array_type)
  inferred_rows <- lapply(seq_len(nrow(targets)), function(i) {
    basename <- as.character(targets$Basename[[i]])
    red_file <- locate_idat_file(basename, "Red")
    idat <- illuminaio::readIDAT(red_file)
    n_probes <- nrow(idat$Quants)
    info <- guess_array_info_from_nprobes(n_probes)
    inferred_array_type <- if (identical(info$array_type, "AUTO")) configured_array_type else info$array_type
    tibble::tibble(
      sample_id = as.character(targets$sample_id[[i]]),
      inferred_n_probes = as.integer(n_probes),
      inferred_array_label = info$array_label,
      inferred_array_type = inferred_array_type,
      import_group = paste(inferred_array_type, n_probes, sep = "_")
    )
  })
  out <- dplyr::left_join(targets, dplyr::bind_rows(inferred_rows), by = "sample_id")
  if (any(out$inferred_array_type == "AUTO")) {
    bad <- out$sample_id[out$inferred_array_type == "AUTO"]
    log_error("Could not infer array type from IDATs for sample_id:", paste(bad, collapse = ", "))
  }
  out
}

load_annotation_df <- function(obj) {
  ann <- tryCatch(minfi::getAnnotation(obj), error = function(e) NULL)
  if (is.null(ann)) return(tibble::tibble(Name = rownames(obj)))
  ann_df <- as.data.frame(ann)
  ann_df$Name <- rownames(ann_df)
  tibble::as_tibble(ann_df)
}

choose_chr_col <- function(ann_df) {
  cols <- intersect(c("chr", "CHR", "seqnames"), names(ann_df))
  if (length(cols) == 0) return(NA_character_)
  cols[[1]]
}

filter_probe_matrices <- function(beta, mval, detp, ann_df, cfg) {
  keep <- rep(TRUE, nrow(beta))
  names(keep) <- rownames(beta)
  removed <- list()
  threshold <- cfg$processing$detection_p_threshold %||% 0.01

  fail_any <- rowMeans(detp > threshold, na.rm = TRUE) > 0
  keep[names(fail_any)] <- keep[names(fail_any)] & !fail_any
  removed$detection_fail <- sum(fail_any)

  if (parse_bool(cfg$filter$remove_snp_probes, default = TRUE) || parse_bool(cfg$filter$remove_cross_reactive, default = FALSE)) {
    if (ncol(mval) < 2) {
      log_warn("Skipping SNP/cross-reactive probe filtering for", ncol(mval), "sample dataset; rmSNPandCH is not robust in this case.")
      filtered_m <- as.matrix(mval)
    } else {
    filtered_m <- tryCatch(
      as.matrix(DMRcate::rmSNPandCH(mval, rmcrosshyb = parse_bool(cfg$filter$remove_cross_reactive, default = FALSE))),
      error = function(e) {
        log_warn("rmSNPandCH failed; skipping SNP/cross-reactive filtering:", conditionMessage(e))
        as.matrix(mval)
      }
    )
    }
    keep <- keep & rownames(beta) %in% rownames(filtered_m)
    removed$snp_crosshyb <- nrow(beta) - nrow(filtered_m)
  } else {
    removed$snp_crosshyb <- 0
  }

  chr_col <- choose_chr_col(ann_df)
  if (!is.na(chr_col) && (parse_bool(cfg$filter$remove_sex_chr, default = FALSE) || parse_bool(cfg$filter$keep_autosomal_only, default = FALSE))) {
    sex_hit <- ann_df$Name[ann_df[[chr_col]] %in% c("chrX", "chrY", "X", "Y")]
    keep[sex_hit] <- FALSE
    removed$sex_chr <- length(intersect(names(keep), sex_hit))
  } else {
    removed$sex_chr <- 0
  }

  beta <- beta[keep, , drop = FALSE]
  mval <- mval[keep, , drop = FALSE]
  ann_df <- ann_df[match(rownames(beta), ann_df$Name), , drop = FALSE]
  list(beta = beta, m = mval, annotation = ann_df, removed = removed)
}

preprocess_single_dataset <- function(dataset_row, samples, cfg) {
  ds_id <- dataset_row$dataset_id[[1]]
  ds_path <- resolve_path(dataset_row$path[[1]])
  ds_array_type <- normalize_array_type(dataset_row$array_type[[1]])
  ds_samples <- samples %>%
    dplyr::filter(.data$dataset_id == ds_id) %>%
    dplyr::filter(parse_bool_vec(.data$include, default = TRUE))
  if (nrow(ds_samples) == 0) {
    log_warn("Dataset", ds_id, "has no included samples; skipping.")
    return(NULL)
  }
  targets <- resolve_sample_basenames(ds_samples, ds_path)
  targets <- infer_target_import_groups(targets, ds_array_type)
  split_targets <- split(targets, targets$import_group, drop = TRUE)

  lapply(names(split_targets), function(import_group) {
    group_targets <- tibble::as_tibble(split_targets[[import_group]])
    group_array_type <- normalize_array_type(group_targets$inferred_array_type[[1]])
    rgset <- minfi::read.metharray.exp(targets = as.data.frame(group_targets), recursive = TRUE, extended = TRUE)
    rgset <- configure_rgset_annotation(rgset, group_array_type, coalesce_chr(cfg$project$genome_build, "hg38"))
    colnames(rgset) <- group_targets$sample_id
    detp <- minfi::detectionP(rgset)
    qc_tbl <- tibble::tibble(
      dataset_id = ds_id,
      import_group = import_group,
      sample_id = colnames(detp),
      mean_detp = colMeans(detp, na.rm = TRUE),
      frac_failed = colMeans(detp > (cfg$processing$detection_p_threshold %||% 0.01), na.rm = TRUE)
    ) %>%
      dplyr::mutate(qc_fail = .data$frac_failed > (cfg$processing$max_failed_probes_fraction %||% 0.01))

    keep_samples <- rep(TRUE, ncol(rgset))
    names(keep_samples) <- colnames(rgset)
    if (parse_bool(cfg$processing$exclude_failed_samples, default = TRUE)) {
      keep_samples[qc_tbl$sample_id] <- !qc_tbl$qc_fail
    }
    rgset <- rgset[, keep_samples, drop = FALSE]
    detp <- detp[, keep_samples, drop = FALSE]
    qc_tbl <- qc_tbl %>% dplyr::mutate(included_for_analysis = .data$sample_id %in% colnames(rgset))

    norm_method <- tolower(coalesce_chr(cfg$processing$normalization, "noob"))
    normset <- switch(
      norm_method,
      noob = minfi::preprocessNoob(rgset),
      quantile = minfi::preprocessQuantile(rgset),
      swan = {
        mset_raw <- minfi::preprocessRaw(rgset)
        minfi::preprocessSwan(rgset, mset = mset_raw)
      },
      funnorm = minfi::preprocessFunnorm(rgset),
      log_error("Unsupported normalization method:", norm_method)
    )

    beta <- minfi::getBeta(normset)
    mval <- minfi::getM(normset)
    ann_df <- load_annotation_df(normset)
    filtered <- filter_probe_matrices(beta, mval, detp, ann_df, cfg)

    sample_meta <- ds_samples %>%
      dplyr::filter(.data$sample_id %in% colnames(filtered$beta)) %>%
      dplyr::left_join(qc_tbl, by = c("sample_id", "dataset_id")) %>%
      dplyr::left_join(
        dplyr::select(group_targets, .data$sample_id, .data$import_group, .data$inferred_n_probes, .data$inferred_array_label, .data$inferred_array_type),
        by = "sample_id"
      )

    list(
      dataset_id = ds_id,
      import_group = import_group,
      inferred_n_probes = group_targets$inferred_n_probes[[1]],
      inferred_array_label = group_targets$inferred_array_label[[1]],
      dataset_path = ds_path,
      array_type = group_array_type,
      normalization = norm_method,
      rgset = rgset,
      detp = detp,
      beta = filtered$beta,
      m = filtered$m,
      annotation = filtered$annotation,
      removed = filtered$removed,
      qc_table = qc_tbl,
      sample_table = sample_meta
    )
  })
}

normalize_probe_ids <- function(ids, array_type) {
  at <- normalize_array_type(array_type)
  out <- as.character(ids)
  if (identical(at, "EPIC_V2")) out <- sub("_[A-Za-z]+[0-9]+$", "", out)
  out
}

collapse_matrix_rows_by_id <- function(mat, probe_ids) {
  ids <- as.character(probe_ids)
  summed <- rowsum(mat, group = ids, reorder = FALSE)
  counts <- as.numeric(table(ids)[rownames(summed)])
  sweep(summed, 1, counts, "/")
}

collapse_annotation_by_id <- function(ann_df, probe_ids) {
  ids <- as.character(probe_ids)
  ann_df$normalized_id <- ids
  ann_df <- ann_df[!duplicated(ann_df$normalized_id), , drop = FALSE]
  ann_df$Name <- ann_df$normalized_id
  ann_df$normalized_id <- NULL
  tibble::as_tibble(ann_df)
}

prepare_dataset_for_merge <- function(run, merge_mode = c("native", "normalized")) {
  merge_mode <- match.arg(merge_mode)
  if (merge_mode == "native") return(run)
  ids <- normalize_probe_ids(rownames(run$beta), run$array_type)
  run$beta <- collapse_matrix_rows_by_id(run$beta, ids)
  run$m <- collapse_matrix_rows_by_id(run$m, ids)
  run$annotation <- collapse_annotation_by_id(as.data.frame(run$annotation), ids)
  run
}

inverse_m_to_beta <- function(m) {
  2^m / (1 + 2^m)
}

combine_processed_datasets <- function(processed, cfg) {
  processed <- Filter(Negate(is.null), processed)
  if (length(processed) == 0) log_error("No datasets left after preprocessing")
  array_types <- unique(vapply(processed, `[[`, character(1), "array_type"))
  merge_mode <- if (length(array_types) == 1 && identical(array_types, "EPIC_V2")) "native" else "normalized"
  runs <- lapply(processed, prepare_dataset_for_merge, merge_mode = merge_mode)
  common_probes <- Reduce(intersect, lapply(runs, function(x) rownames(x$beta)))
  if (length(common_probes) == 0) log_error("No shared probes remain across enabled datasets")
  sample_ids <- unlist(lapply(runs, function(x) as.character(x$sample_table$sample_id)))
  dup <- unique(sample_ids[duplicated(sample_ids)])
  if (length(dup) > 0) log_error("Duplicate sample_id across datasets:", paste(dup, collapse = ", "))

  runs <- lapply(runs, function(x) {
    x$beta <- x$beta[common_probes, , drop = FALSE]
    x$m <- x$m[common_probes, , drop = FALSE]
    x$annotation <- x$annotation[match(common_probes, x$annotation$Name), , drop = FALSE]
    x
  })

  beta <- do.call(cbind, lapply(runs, `[[`, "beta"))
  mval <- do.call(cbind, lapply(runs, `[[`, "m"))
  sample_data <- dplyr::bind_rows(lapply(runs, `[[`, "sample_table"))
  ann <- runs[[1]]$annotation
  run_summary <- dplyr::bind_rows(lapply(runs, function(x) {
    tibble::tibble(
      dataset_id = x$dataset_id,
      import_group = x$import_group %||% x$dataset_id,
      inferred_n_probes = x$inferred_n_probes %||% NA_integer_,
      inferred_array_label = x$inferred_array_label %||% NA_character_,
      array_type = x$array_type,
      n_samples = ncol(x$beta),
      n_common_probes = nrow(x$beta),
      normalization = x$normalization
    )
  }))
  list(
    beta = beta,
    m = mval,
    annotation = ann,
    sample_data = sample_data,
    run_summary = run_summary,
    array_types = array_types,
    dmr_array_type = normalize_array_type_for_dmr(array_types),
    gometh_array_type = normalize_array_type_for_gometh(array_types),
    merge_mode = merge_mode
  )
}

build_design_matrix <- function(meta, preserve_cols) {
  preserve_cols <- preserve_cols[preserve_cols %in% names(meta)]
  if (length(preserve_cols) == 0) return(NULL)
  design_df <- meta[, preserve_cols, drop = FALSE]
  design_df[] <- lapply(design_df, function(x) if (is.character(x)) factor(x) else x)
  stats::model.matrix(stats::as.formula(paste("~", paste(preserve_cols, collapse = " + "))), data = design_df)
}

apply_batch_correction <- function(obj, cfg) {
  bc_cfg <- cfg$batch_correction
  if (is.null(bc_cfg) || !parse_bool(bc_cfg$enabled, default = FALSE)) {
    obj$beta_active <- obj$beta
    obj$m_active <- obj$m
    obj$batch_correction <- list(enabled = FALSE)
    return(obj)
  }
  batch_col <- coalesce_chr(bc_cfg$batch_column, "batch")
  meta <- obj$sample_data
  if (!(batch_col %in% names(meta))) {
    log_warn("Batch correction skipped; missing batch column", batch_col)
    obj$beta_active <- obj$beta
    obj$m_active <- obj$m
    obj$batch_correction <- list(enabled = FALSE, note = "batch_column_missing")
    return(obj)
  }
  batch <- meta[[batch_col]]
  keep <- !is.na(batch) & trimws(as.character(batch)) != ""
  if (!all(keep)) {
    log_warn("Batch correction skipped; missing values in", batch_col)
    obj$beta_active <- obj$beta
    obj$m_active <- obj$m
    obj$batch_correction <- list(enabled = FALSE, note = "batch_values_missing")
    return(obj)
  }
  batch <- factor(as.character(batch))
  if (length(unique(batch)) < 2) {
    log_warn("Batch correction skipped; fewer than two batch levels in", batch_col)
    obj$beta_active <- obj$beta
    obj$m_active <- obj$m
    obj$batch_correction <- list(enabled = FALSE, note = "single_batch")
    return(obj)
  }
  preserve_cols <- unique(c("group", config_chr_vector(bc_cfg$preserve_columns)))
  preserve_cols <- setdiff(preserve_cols, batch_col)
  design <- build_design_matrix(meta, preserve_cols)
  method <- coalesce_chr(bc_cfg$method, "limma_removeBatchEffect")
  corrected_m <- switch(
    method,
    limma_removeBatchEffect = limma::removeBatchEffect(obj$m, batch = batch, design = design),
    Combat = {
      mod <- design
      sva::ComBat(dat = obj$m, batch = batch, mod = mod, par.prior = TRUE, prior.plots = FALSE)
    },
    log_error("Unsupported batch correction method:", method)
  )
  obj$m_active <- corrected_m
  obj$beta_active <- inverse_m_to_beta(corrected_m)
  obj$batch_correction <- list(
    enabled = TRUE,
    method = method,
    batch_column = batch_col,
    preserve_columns = preserve_cols
  )
  obj
}

embedding_palette <- function(values) {
  vals <- sort(unique(as.character(stats::na.omit(values))))
  if (length(vals) == 0) return(character(0))
  stats::setNames(grDevices::hcl.colors(length(vals), "Dark 3"), vals)
}

theme_pub <- function() {
  ggplot2::theme_minimal(base_size = 14) +
    ggplot2::theme(
      plot.title = ggplot2::element_text(face = "bold", size = 17, hjust = 0),
      plot.subtitle = ggplot2::element_text(color = "#4A4A4A", hjust = 0),
      axis.title = ggplot2::element_text(face = "bold"),
      axis.text = ggplot2::element_text(color = "#222222"),
      panel.grid.major.x = ggplot2::element_line(color = "#E5E5E5", linewidth = 0.25),
      panel.grid.major.y = ggplot2::element_line(color = "#EFEFEF", linewidth = 0.25),
      panel.grid.minor = ggplot2::element_blank(),
      legend.position = "top",
      legend.title = ggplot2::element_text(face = "bold"),
      plot.margin = ggplot2::margin(10, 14, 10, 10)
    )
}

build_embedding_plot <- function(df, x, y, color_var, title) {
  palette_vals <- embedding_palette(df[[color_var]])
  ggplot2::ggplot(df, ggplot2::aes(.data[[x]], .data[[y]], color = .data[[color_var]])) +
    ggplot2::geom_point(size = 3, alpha = 0.9) +
    ggplot2::scale_color_manual(values = palette_vals) +
    ggplot2::labs(title = title, subtitle = paste(nrow(df), "samples"), x = x, y = y, color = color_var) +
    theme_pub()
}

embedding_hover_text <- function(df, axis_labels) {
  out <- paste0(
    "<b>", df$sample_id, "</b><br>",
    "Group: ", df$group, "<br>",
    "Batch: ", df$batch, "<br>",
    axis_labels[[1]], ": ", sprintf("%.3f", df[[axis_labels[[1]]]]), "<br>",
    axis_labels[[2]], ": ", sprintf("%.3f", df[[axis_labels[[2]]]])
  )
  if (length(axis_labels) >= 3) {
    out <- paste0(out, "<br>", axis_labels[[3]], ": ", sprintf("%.3f", df[[axis_labels[[3]]]]))
  }
  out
}

build_plotly_3d <- function(df, x, y, z, color_var, title) {
  palette_vals <- embedding_palette(df[[color_var]])
  df$hover_text <- embedding_hover_text(df, c(x, y, z))
  plotly::layout(
    plotly::plot_ly(
      data = df,
      x = stats::as.formula(paste0("~`", x, "`")),
      y = stats::as.formula(paste0("~`", y, "`")),
      z = stats::as.formula(paste0("~`", z, "`")),
      type = "scatter3d",
      mode = "markers",
      color = stats::as.formula(paste0("~`", color_var, "`")),
      colors = unname(palette_vals),
      text = ~hover_text,
      hoverinfo = "text",
      marker = list(size = 4.5, opacity = 0.85)
    ),
    title = list(text = title),
    legend = list(orientation = "h", y = -0.15),
    scene = list(xaxis = list(title = x), yaxis = list(title = y), zaxis = list(title = z))
  )
}

compute_embeddings <- function(beta, meta, prefix, cfg) {
  n_keep <- min(as.integer(cfg$processing$top_variable_cpg %||% 5000), nrow(beta))
  var_idx <- order(matrixStats::rowVars(beta), decreasing = TRUE)
  if (length(var_idx) > n_keep) var_idx <- var_idx[seq_len(n_keep)]
  beta_var <- beta[var_idx, , drop = FALSE]
  embedding_input <- t(beta_var)
  sample_id_order <- rownames(embedding_input)
  meta <- meta[match(sample_id_order, meta$sample_id), , drop = FALSE]

  set.seed(42)
  pc <- stats::prcomp(embedding_input, center = TRUE, scale. = FALSE)
  pca_df <- tibble::as_tibble(pc$x[, 1:3, drop = FALSE])
  pca_df$sample_id <- sample_id_order
  pca_df <- dplyr::left_join(pca_df, meta, by = "sample_id")

  tsne_perplexity <- min(30, max(1, floor((nrow(embedding_input) - 1) / 3)))
  set.seed(42)
  tsne_fit <- Rtsne::Rtsne(embedding_input, dims = 3, perplexity = tsne_perplexity, pca = TRUE, check_duplicates = FALSE, verbose = FALSE)
  tsne_df <- tibble::as_tibble(tsne_fit$Y)
  colnames(tsne_df) <- c("TSNE1", "TSNE2", "TSNE3")
  tsne_df$sample_id <- sample_id_order
  tsne_df <- dplyr::left_join(tsne_df, meta, by = "sample_id")

  write_table(pca_df, file.path("results/tables", paste0(prefix, "_pca.csv")))
  write_table(tsne_df, file.path("results/tables", paste0(prefix, "_tsne.csv")))

  save_plot(build_embedding_plot(pca_df, "PC1", "PC2", "group", paste(prefix, "PCA by group")), file.path("results/figures", paste0(prefix, "_pca_group.png")), width = 9, height = 6)
  save_plot(build_embedding_plot(pca_df, "PC1", "PC2", "batch", paste(prefix, "PCA by batch")), file.path("results/figures", paste0(prefix, "_pca_batch.png")), width = 9, height = 6)
  save_plot(build_embedding_plot(tsne_df, "TSNE1", "TSNE2", "group", paste(prefix, "t-SNE by group")), file.path("results/figures", paste0(prefix, "_tsne_group.png")), width = 9, height = 6)
  save_plot(build_embedding_plot(tsne_df, "TSNE1", "TSNE2", "batch", paste(prefix, "t-SNE by batch")), file.path("results/figures", paste0(prefix, "_tsne_batch.png")), width = 9, height = 6)
  save_widget(build_plotly_3d(pca_df, "PC1", "PC2", "PC3", "group", paste(prefix, "3D PCA by group")), file.path("results/figures", paste0(prefix, "_pca3d_group.html")))
  save_widget(build_plotly_3d(tsne_df, "TSNE1", "TSNE2", "TSNE3", "group", paste(prefix, "3D t-SNE by group")), file.path("results/figures", paste0(prefix, "_tsne3d_group.html")))
  save_widget(build_plotly_3d(pca_df, "PC1", "PC2", "PC3", "batch", paste(prefix, "3D PCA by batch")), file.path("results/figures", paste0(prefix, "_pca3d_batch.html")))
  save_widget(build_plotly_3d(tsne_df, "TSNE1", "TSNE2", "TSNE3", "batch", paste(prefix, "3D t-SNE by batch")), file.path("results/figures", paste0(prefix, "_tsne3d_batch.html")))

  if (parse_bool(cfg$embeddings$enable_umap, default = TRUE)) {
    set.seed(42)
    umap_coords <- uwot::umap(
      embedding_input,
      n_components = 3,
      n_neighbors = min(15, max(2, nrow(embedding_input) - 1)),
      min_dist = 0.2,
      metric = "euclidean",
      init = "spca",
      verbose = FALSE
    )
    umap_df <- tibble::as_tibble(umap_coords)
    colnames(umap_df) <- c("UMAP1", "UMAP2", "UMAP3")
    umap_df$sample_id <- sample_id_order
    umap_df <- dplyr::left_join(umap_df, meta, by = "sample_id")
    write_table(umap_df, file.path("results/tables", paste0(prefix, "_umap.csv")))
    save_plot(build_embedding_plot(umap_df, "UMAP1", "UMAP2", "group", paste(prefix, "UMAP by group")), file.path("results/figures", paste0(prefix, "_umap_group.png")), width = 9, height = 6)
    save_widget(build_plotly_3d(umap_df, "UMAP1", "UMAP2", "UMAP3", "group", paste(prefix, "3D UMAP by group")), file.path("results/figures", paste0(prefix, "_umap3d_group.html")))
  }
}

apply_comparison_filter <- function(meta, expr_text) {
  if (is.null(expr_text) || !nzchar(trimws(expr_text))) return(rep(TRUE, nrow(meta)))
  env <- list2env(as.list(meta), parent = baseenv())
  out <- tryCatch(eval(parse(text = expr_text), envir = env), error = function(e) log_error("Invalid sample_filter:", expr_text, "|", conditionMessage(e)))
  if (!is.logical(out) || length(out) != nrow(meta)) log_error("sample_filter must return one logical value per sample")
  out
}

theme_pub_volcano <- function() {
  ggplot2::theme_minimal(base_size = 14) +
    ggplot2::theme(
      plot.title = ggplot2::element_text(face = "bold", size = 18, hjust = 0),
      plot.subtitle = ggplot2::element_text(color = "#4A4A4A", size = 11, hjust = 0),
      axis.title = ggplot2::element_text(face = "bold"),
      axis.text = ggplot2::element_text(color = "#222222"),
      panel.grid.minor = ggplot2::element_blank(),
      panel.grid.major.x = ggplot2::element_blank(),
      legend.position = "top",
      legend.title = ggplot2::element_blank(),
      legend.text = ggplot2::element_text(size = 10),
      plot.margin = ggplot2::margin(10, 14, 10, 10)
    )
}

format_report_title <- function(report_index, name) {
  title_body <- gsub("_", " ", trimws(as.character(name)))
  sprintf("%02d %s", as.integer(report_index), title_body)
}

build_dmp_volcano_plot <- function(res, cmp_name, base_group, target_group, cmp_alpha, cmp_delta) {
  plot_df <- dplyr::mutate(
    res,
    neg_log10_p = -log10(pmax(P.Value, .Machine$double.xmin)),
    direction = dplyr::case_when(
      adj.P.Val <= cmp_alpha & delta_beta >= cmp_delta ~ "target_hypermethylated",
      adj.P.Val <= cmp_alpha & delta_beta <= -cmp_delta ~ "target_hypomethylated",
      TRUE ~ "Not significant"
    )
  )
  label_col <- intersect(c("UCSC_RefGene_Name", "GeneSymbol", "SYMBOL"), names(plot_df))[1]
  if (is.na(label_col) || length(label_col) == 0) {
    plot_df$label_text <- plot_df$CpG
  } else {
    plot_df$label_text <- sub(";.*$", "", dplyr::coalesce(as.character(plot_df[[label_col]]), plot_df$CpG))
  }
  label_tbl <- plot_df %>%
    dplyr::filter(.data$direction != "Not significant") %>%
    dplyr::arrange(.data$adj.P.Val, -abs(.data$delta_beta)) %>%
    dplyr::distinct(.data$label_text, .keep_all = TRUE) %>%
    dplyr::slice_head(n = 12)

  palette_vals <- c("Not significant" = "#C9CED6", "target_hypermethylated" = "#B22222", "target_hypomethylated" = "#1F5A94")
  ggplot2::ggplot(plot_df, ggplot2::aes(x = .data$delta_beta, y = .data$neg_log10_p)) +
    ggplot2::geom_vline(xintercept = c(-cmp_delta, cmp_delta), linetype = "dashed", linewidth = 0.4, color = "#7F7F7F") +
    ggplot2::geom_hline(yintercept = -log10(cmp_alpha), linetype = "dashed", linewidth = 0.4, color = "#7F7F7F") +
    ggplot2::geom_point(ggplot2::aes(color = .data$direction), alpha = 0.9, size = 1.5) +
    ggrepel::geom_text_repel(data = label_tbl, ggplot2::aes(label = .data$label_text, color = .data$direction), size = 3.3, show.legend = FALSE, max.overlaps = Inf) +
    ggplot2::scale_color_manual(values = palette_vals) +
    ggplot2::labs(title = cmp_name, subtitle = paste0(target_group, " vs ", base_group), x = paste0("Delta beta (", target_group, " - ", base_group, ")"), y = expression(-log[10](italic(P)))) +
    theme_pub_volcano()
}

run_differential_analysis <- function(obj, comparisons, cfg) {
  beta <- obj$beta_active
  mval <- obj$m_active
  meta <- obj$sample_data
  ann <- obj$annotation
  out_summary <- list()
  out_results <- list()
  manifests <- list()

  for (i in seq_len(nrow(comparisons))) {
    cmp <- comparisons[i, , drop = FALSE]
    if (!parse_bool(cmp$enabled[[1]], default = TRUE)) next
    cmp_id <- cmp$comparison_id[[1]]
    cmp_name <- cmp$name[[1]]
    target_group <- cmp$target_group[[1]]
    base_group <- cmp$base_group[[1]]
    cmp_alpha <- if (is.finite(cmp$alpha[[1]])) cmp$alpha[[1]] else 0.05
    cmp_delta <- if (is.finite(cmp$delta_beta_min[[1]])) cmp$delta_beta_min[[1]] else 0.10
    cmp_covars <- trimws(unlist(strsplit(coalesce_chr(cmp$covariates, ""), "[,;]")))
    cmp_covars <- cmp_covars[nzchar(cmp_covars)]

    subset_keep <- apply_comparison_filter(meta, coalesce_chr(cmp$sample_filter, ""))
    group_keep <- meta$group %in% c(base_group, target_group)
    keep <- subset_keep & group_keep
    meta2 <- meta[keep, , drop = FALSE]
    if (nrow(meta2) == 0) next
    meta2$group <- factor(meta2$group, levels = c(base_group, target_group))
    counts <- table(meta2$group)
    if (as.integer(counts[[base_group]]) < 2 || as.integer(counts[[target_group]]) < 2) {
      log_warn("Skipping comparison", cmp_id, "because one group has fewer than two samples")
      next
    }
    sample_ids <- meta2$sample_id
    mat_beta <- beta[, sample_ids, drop = FALSE]
    mat_m <- mval[, sample_ids, drop = FALSE]
    design_vars <- c("group", intersect(cmp_covars, names(meta2)))
    design <- model.matrix(stats::as.formula(paste("~", paste(design_vars, collapse = " + "))), data = meta2)
    fit <- limma::lmFit(mat_m, design)
    fit <- limma::eBayes(fit)
    coef_name <- colnames(design)[grepl("^group", colnames(design))][1]
    if (is.na(coef_name) || !nzchar(coef_name)) next
    res <- limma::topTable(fit, coef = coef_name, number = Inf, sort.by = "P", adjust.method = "BH")
    res$CpG <- rownames(res)
    res$delta_beta <- rowMeans(mat_beta[, meta2$group == target_group, drop = FALSE], na.rm = TRUE) -
      rowMeans(mat_beta[, meta2$group == base_group, drop = FALSE], na.rm = TRUE)
    res <- tibble::as_tibble(res) %>% dplyr::left_join(ann, by = c("CpG" = "Name"))
    res <- res %>%
      dplyr::mutate(
        comparison_id = cmp_id,
        comparison_name = cmp_name,
        target_group = target_group,
        base_group = base_group,
        significant = adj.P.Val <= cmp_alpha & abs(delta_beta) >= cmp_delta,
        direction = dplyr::case_when(
          significant & delta_beta >= cmp_delta ~ "target_hypermethylated",
          significant & delta_beta <= -cmp_delta ~ "target_hypomethylated",
          TRUE ~ "not_significant"
        ),
        CpG_base = sub("_[A-Za-z]+[0-9]+$", "", .data$CpG)
      )

    cmp_dir_tbl <- file.path("results/tables/comparisons", cmp_id)
    cmp_dir_fig <- file.path("results/figures/comparisons", cmp_id)
    dir.create(cmp_dir_tbl, recursive = TRUE, showWarnings = FALSE)
    dir.create(cmp_dir_fig, recursive = TRUE, showWarnings = FALSE)
    write_table(res, file.path(cmp_dir_tbl, "dmp_table.csv"))
    write_table(dplyr::filter(res, .data$significant), file.path(cmp_dir_tbl, "dmp_significant.csv"))
    write_table(meta2, file.path(cmp_dir_tbl, "sample_manifest.csv"))
    p <- build_dmp_volcano_plot(res, cmp_name, base_group, target_group, cmp_alpha, cmp_delta)
    save_plot(p, file.path(cmp_dir_fig, "dmp_volcano.png"), width = 8.6, height = 5.8)

    out_results[[cmp_id]] <- res
    out_summary[[cmp_id]] <- tibble::tibble(
      comparison_id = cmp_id,
      comparison_name = cmp_name,
      target_group = target_group,
      base_group = base_group,
      n_target = as.integer(counts[[target_group]]),
      n_base = as.integer(counts[[base_group]]),
      n_total = nrow(meta2),
      n_sig_cpg = sum(res$significant, na.rm = TRUE),
      n_target_hyper = sum(res$direction == "target_hypermethylated", na.rm = TRUE),
      n_target_hypo = sum(res$direction == "target_hypomethylated", na.rm = TRUE)
    )
    manifests[[cmp_id]] <- meta2
  }

  if (length(out_results) == 0) log_error("No comparisons produced DMP output")
  dmp_summary <- dplyr::bind_rows(out_summary)
  dmp_all <- dplyr::bind_rows(out_results)
  save_rds(out_results, "results/rds/dmp_by_comparison.rds")
  write_table(dmp_summary, "results/tables/dmp_comparisons_summary.csv")
  write_table(dmp_all, "results/tables/dmp_all_comparisons.csv")
  list(summary = dmp_summary, results = out_results, all = dmp_all, manifests = manifests)
}

run_dmr_analysis <- function(obj, comparisons, dmp_results, cfg) {
  if (!parse_bool(cfg$dmr$enabled, default = TRUE)) return(NULL)
  meta <- obj$sample_data
  mat_m <- obj$m_active
  dmr_tables <- list()
  dmr_summary <- list()

  for (cmp_id in names(dmp_results$results)) {
    cmp <- comparisons[comparisons$comparison_id == cmp_id, , drop = FALSE]
    meta2 <- dmp_results$manifests[[cmp_id]]
    target_group <- cmp$target_group[[1]]
    base_group <- cmp$base_group[[1]]
    cmp_covars <- trimws(unlist(strsplit(coalesce_chr(cmp$covariates, ""), "[,;]")))
    cmp_covars <- cmp_covars[nzchar(cmp_covars)]
    sample_ids <- meta2$sample_id
    mat2 <- mat_m[, sample_ids, drop = FALSE]
    meta2$group <- factor(meta2$group, levels = c(base_group, target_group))
    design <- model.matrix(stats::as.formula(paste("~", paste(c("group", intersect(cmp_covars, names(meta2))), collapse = " + "))), data = meta2)
    coef_name <- colnames(design)[grepl("^group", colnames(design))][1]
    if (is.na(coef_name) || !nzchar(coef_name)) next

    dmr_array_type <- resolve_dmrcate_array_type(rownames(mat2), obj$dmr_array_type)
    ensure_annotation_package_loaded(dmr_array_type, tool = "dmr")
    ann_obj <- tryCatch({
      if (identical(dmr_array_type, "EPICv2")) {
        DMRcate::cpg.annotate(
          "array",
          object = mat2,
          what = "M",
          arraytype = dmr_array_type,
          analysis.type = "differential",
          design = design,
          coef = which(colnames(design) == coef_name),
          fdr = cfg$dmr$fdr %||% 0.05,
          epicv2Filter = coalesce_chr(cfg$dmr$epicv2_filter, "mean"),
          epicv2Remap = parse_bool(cfg$dmr$epicv2_remap, default = TRUE)
        )
      } else {
        DMRcate::cpg.annotate(
          "array",
          object = mat2,
          what = "M",
          arraytype = dmr_array_type,
          analysis.type = "differential",
          design = design,
          coef = which(colnames(design) == coef_name),
          fdr = cfg$dmr$fdr %||% 0.05
        )
      }
    }, error = function(e) {
      log_warn("DMRcate cpg.annotate failed for", cmp_id, ":", conditionMessage(e))
      NULL
    })
    if (is.null(ann_obj)) next
    dmr_fit <- tryCatch(DMRcate::dmrcate(ann_obj, lambda = cfg$dmr$lambda %||% 1000, C = cfg$dmr$C %||% 2), error = function(e) {
      log_warn("dmrcate failed for", cmp_id, ":", conditionMessage(e))
      NULL
    })
    if (is.null(dmr_fit)) next
    ranges <- DMRcate::extractRanges(dmr_fit, genome = coalesce_chr(cfg$project$genome_build, "hg38"))
    dmr_tbl <- as.data.frame(ranges)
    if (nrow(dmr_tbl) == 0) next
    dmr_tbl <- tibble::as_tibble(dmr_tbl) %>%
      dplyr::mutate(
        comparison_id = cmp_id,
        direction = dplyr::case_when(
          meandiff >= 0 ~ "target_hypermethylated",
          TRUE ~ "target_hypomethylated"
        ),
        region_id = paste0(cmp_id, "_DMR", seq_len(dplyr::n()))
      )
    cmp_dir_tbl <- file.path("results/tables/comparisons", cmp_id)
    cmp_dir_fig <- file.path("results/figures/comparisons", cmp_id)
    dir.create(cmp_dir_tbl, recursive = TRUE, showWarnings = FALSE)
    dir.create(cmp_dir_fig, recursive = TRUE, showWarnings = FALSE)
    write_table(dmr_tbl, file.path(cmp_dir_tbl, "dmr_table.csv"))
    plot_tbl <- dmr_tbl %>% dplyr::arrange(.data$HMFDR) %>% dplyr::slice_head(n = 15) %>%
      dplyr::mutate(region_id = factor(.data$region_id, levels = rev(.data$region_id)))
    p <- ggplot2::ggplot(plot_tbl, ggplot2::aes(x = -log10(pmax(.data$HMFDR, .Machine$double.xmin)), y = .data$region_id, fill = .data$direction)) +
      ggplot2::geom_col(width = 0.72) +
      ggplot2::scale_fill_manual(values = c(target_hypermethylated = "#B22222", target_hypomethylated = "#1F5A94")) +
      ggplot2::labs(title = cmp$name[[1]], subtitle = "Top DMRs ranked by -log10(HMFDR)", x = "-log10(HMFDR)", y = NULL) +
      theme_pub()
    save_plot(p, file.path(cmp_dir_fig, "dmr_ranked.png"), width = 8.6, height = 5.8)
    dmr_tables[[cmp_id]] <- dmr_tbl
    dmr_summary[[cmp_id]] <- tibble::tibble(
      comparison_id = cmp_id,
      comparison_name = cmp$name[[1]],
      n_regions = nrow(dmr_tbl),
      best_hmfdr = min(dmr_tbl$HMFDR, na.rm = TRUE),
      n_target_hyper = sum(dmr_tbl$direction == "target_hypermethylated", na.rm = TRUE),
      n_target_hypo = sum(dmr_tbl$direction == "target_hypomethylated", na.rm = TRUE)
    )
  }

  if (length(dmr_tables) == 0) {
    write_table(tibble::tibble(note = "No DMR results were produced."), "results/tables/dmr_summary.csv")
    return(NULL)
  }
  dmr_summary_tbl <- dplyr::bind_rows(dmr_summary)
  write_table(dmr_summary_tbl, "results/tables/dmr_summary.csv")
  save_rds(dmr_tables, "results/rds/dmr_by_comparison.rds")
  list(summary = dmr_summary_tbl, results = dmr_tables)
}

run_enrichment_analysis <- function(obj, dmp_results, cfg) {
  if (!parse_bool(cfg$enrichment$enabled, default = TRUE)) return(NULL)
  collections <- config_chr_vector(cfg$enrichment$collections)
  if (length(collections) == 0) collections <- c("GO", "KEGG")
  all_cpg <- unique(sub("_[A-Za-z]+[0-9]+$", "", rownames(obj$beta_active)))
  summaries <- list()

  for (cmp_id in names(dmp_results$results)) {
    res <- dmp_results$results[[cmp_id]]
    cmp_dir_tbl <- file.path("results/tables/comparisons", cmp_id)
    dir.create(cmp_dir_tbl, recursive = TRUE, showWarnings = FALSE)
    for (direction in c("target_hypermethylated", "target_hypomethylated")) {
      sig <- unique(sub("_[A-Za-z]+[0-9]+$", "", res$CpG[res$direction == direction]))
      if (length(sig) < 5) next
      for (collection in collections) {
      gometh_array_type <- resolve_gometh_array_type(rownames(obj$beta_active), obj$gometh_array_type)
      ensure_annotation_package_loaded(gometh_array_type, tool = "gometh")
      enr <- tryCatch(
        missMethyl::gometh(sig.cpg = sig, all.cpg = all_cpg, collection = collection, array.type = gometh_array_type),
        error = function(e) {
          log_warn("gometh failed for", cmp_id, direction, collection, ":", conditionMessage(e))
          NULL
          }
        )
        if (is.null(enr)) next
        enr <- tibble::as_tibble(enr) %>%
          dplyr::mutate(comparison_id = cmp_id, direction = direction, collection = collection)
        out_path <- file.path(cmp_dir_tbl, paste0("enrichment_", tolower(collection), "_", direction, ".csv"))
        write_table(enr, out_path)
        summaries[[paste(cmp_id, direction, collection, sep = "_")]] <- enr %>% dplyr::slice_head(n = cfg$enrichment$top_n %||% 30)
      }
    }
  }

  if (length(summaries) == 0) {
    write_table(tibble::tibble(note = "No enrichment results were produced."), "results/tables/enrichment_summary.csv")
    return(NULL)
  }
  summary_tbl <- dplyr::bind_rows(summaries)
  write_table(summary_tbl, "results/tables/enrichment_summary.csv")
  summary_tbl
}

match_probe_ids <- function(query_ids, row_ids) {
  row_base <- sub("_[A-Za-z]+[0-9]+$", "", row_ids)
  unique(unlist(lapply(query_ids, function(id) row_ids[row_ids == id | row_base == id])))
}

run_drilldown <- function(obj, cfg) {
  if (!parse_bool(cfg$drilldown$enabled, default = TRUE)) return(NULL)
  beta <- obj$beta_active
  ann <- obj$annotation
  meta <- obj$sample_data
  drill_cfg <- cfg$drilldown
  selected <- list()

  cpg_ids <- config_chr_vector(drill_cfg$cpg_ids)
  if (length(cpg_ids) > 0) {
    matched <- match_probe_ids(cpg_ids, rownames(beta))
    if (length(matched) > 0) selected$cpgs <- matched
  }

  genes <- config_chr_vector(drill_cfg$genes)
  if (length(genes) > 0) {
    gene_col <- intersect(c("UCSC_RefGene_Name", "GeneSymbol", "SYMBOL"), names(ann))[1]
    if (!is.na(gene_col) && length(gene_col) > 0) {
      gene_hits <- ann$Name[vapply(strsplit(as.character(ann[[gene_col]]), ";"), function(parts) any(parts %in% genes), logical(1))]
      selected$genes <- unique(gene_hits)
    }
  }

  loci <- config_chr_vector(drill_cfg$loci)
  if (length(loci) > 0) {
    chr_col <- choose_chr_col(ann)
    pos_col <- intersect(c("pos", "Position"), names(ann))[1]
    if (!is.na(chr_col) && !is.na(pos_col)) {
      hits <- character(0)
      for (locus in loci) {
        loc_match <- stringr::str_match(locus, "^([^:]+):(\\d+)-(\\d+)$")
        if (any(is.na(loc_match))) next
        chr <- loc_match[, 2]
        start <- as.numeric(loc_match[, 3])
        end <- as.numeric(loc_match[, 4])
        hits <- c(hits, ann$Name[ann[[chr_col]] == chr & ann[[pos_col]] >= start & ann[[pos_col]] <= end])
      }
      selected$loci <- unique(hits)
    }
  }

  drill_rows <- unique(unlist(selected))
  if (length(drill_rows) == 0) {
    write_table(tibble::tibble(note = "No drilldown probes were selected."), "results/tables/drilldown_summary.csv")
    return(NULL)
  }

  drill_beta <- beta[drill_rows, , drop = FALSE]
  write_table(tibble::rownames_to_column(as.data.frame(drill_beta), "CpG"), "results/tables/drilldown_beta_matrix.csv")
  write_table(meta, "results/tables/drilldown_sample_metadata.csv")
  heatmap_n <- min(nrow(drill_beta), drill_cfg$heatmap_top_var %||% 100)
  heatmap_mat <- drill_beta[seq_len(heatmap_n), , drop = FALSE]
  heatmap_mat_scaled <- t(scale(t(heatmap_mat)))
  heatmap_mat_scaled[is.na(heatmap_mat_scaled)] <- 0
  annotation_df <- data.frame(group = meta$group, batch = meta$batch, row.names = meta$sample_id, stringsAsFactors = FALSE)
  pheatmap::pheatmap(heatmap_mat_scaled, annotation_col = annotation_df, filename = "results/figures/drilldown_heatmap.png", width = 10, height = 8)
  write_table(tibble::tibble(category = names(selected), n_cpg = vapply(selected, length, integer(1))), "results/tables/drilldown_summary.csv")
  list(selected = selected)
}

run_methylation_analysis <- function(cfg, samples, comparisons) {
  ensure_dirs(".")
  validate_workspace(cfg, samples, comparisons)

  datasets <- datasets_to_tibble(cfg) %>% dplyr::filter(.data$enabled)
  active_samples <- samples %>% dplyr::filter(parse_bool_vec(.data$include, default = TRUE))
  processed <- unlist(lapply(seq_len(nrow(datasets)), function(i) preprocess_single_dataset(datasets[i, , drop = FALSE], active_samples, cfg)), recursive = FALSE)
  processed <- Filter(Negate(is.null), processed)
  if (length(processed) == 0) log_error("No datasets were successfully preprocessed")

  qc_tables <- dplyr::bind_rows(lapply(processed, `[[`, "qc_table"))
  write_table(qc_tables, "results/tables/qc_metrics.csv")
  filter_summary <- dplyr::bind_rows(lapply(processed, function(x) tibble::tibble(dataset_id = x$dataset_id, import_group = x$import_group %||% x$dataset_id, !!!x$removed)))
  write_table(filter_summary, "results/tables/filter_summary.csv")

  combined <- combine_processed_datasets(processed, cfg)
  write_table(combined$run_summary, "results/tables/input_run_summary.csv")
  write_table(combined$sample_data, "results/tables/sample_inventory.csv")
  save_rds(combined, "results/rds/combined_raw.rds")

  compute_embeddings(combined$beta, combined$sample_data, "raw_all_samples", cfg)
  combined <- apply_batch_correction(combined, cfg)
  batch_tbl <- tibble::tibble(
    metric = c("enabled", "method", "batch_column", "preserve_columns"),
    value = c(
      as.character(combined$batch_correction$enabled %||% FALSE),
      coalesce_chr(combined$batch_correction$method, NA_character_),
      coalesce_chr(combined$batch_correction$batch_column, NA_character_),
      paste(combined$batch_correction$preserve_columns %||% character(0), collapse = ", ")
    )
  )
  write_table(batch_tbl, "results/tables/batch_correction_summary.csv")
  if (isTRUE(combined$batch_correction$enabled)) {
    compute_embeddings(combined$beta_active, combined$sample_data, "corrected_all_samples", cfg)
  }
  save_rds(combined, "results/rds/combined_active.rds")

  dmp_results <- run_differential_analysis(combined, comparisons, cfg)
  dmr_results <- run_dmr_analysis(combined, comparisons, dmp_results, cfg)
  enrichment_results <- run_enrichment_analysis(combined, dmp_results, cfg)
  drilldown_results <- run_drilldown(combined, cfg)

  render_reports(cfg)
  invisible(list(combined = combined, dmp = dmp_results, dmr = dmr_results, enrichment = enrichment_results, drilldown = drilldown_results))
}

render_reports <- function(cfg) {
  report_files <- c(
    "00_study_overview.qmd",
    "01_input_qc.qmd",
    "02_all_samples_embeddings.qmd",
    "03_differential_methylation.qmd",
    "04_differential_regions.qmd",
    "05_enrichment.qmd",
    "06_drilldown.qmd"
  )
  for (file in report_files) {
    quarto_render_cli(file, output_dir = "reports")
  }
}

select_report_columns <- function(df, preferred = NULL, max_extra = 0) {
  if (is.null(preferred) || length(preferred) == 0) return(df)
  keep <- intersect(preferred, names(df))
  if (max_extra > 0) keep <- c(keep, head(setdiff(names(df), keep), max_extra))
  if (length(keep) == 0) return(df)
  df[, keep, drop = FALSE]
}

format_report_table <- function(df) {
  tbl <- as.data.frame(df, stringsAsFactors = FALSE)
  if (nrow(tbl) == 0) return(tbl)
  for (nm in names(tbl)) {
    col <- tbl[[nm]]
    if (!is.numeric(col)) next
    nm_lower <- tolower(nm)
    if (nm_lower %in% c("p.value", "adj.p.val", "hmfdr", "fdr", "qvalue", "pvalue")) {
      tbl[[nm]] <- ifelse(is.na(col), NA_character_, formatC(col, format = "e", digits = 2))
    } else if (nm_lower %in% c("delta_beta", "logfc", "meandiff", "maxdiff")) {
      tbl[[nm]] <- ifelse(is.na(col), NA_character_, formatC(col, format = "f", digits = 3))
    } else {
      tbl[[nm]] <- ifelse(is.na(col), NA_character_, format(round(col, 0), big.mark = ",", trim = TRUE, scientific = FALSE))
    }
  }
  tbl
}

report_asset_href <- function(path) {
  p <- as.character(path[[1]])
  p
}

report_download_href <- function(path) {
  p <- as.character(path[[1]])
  if (startsWith(p, "results/")) return(file.path("..", p))
  p
}

report_download_link <- function(path, label = "Download CSV") {
  htmltools::tags$p(
    style = "margin: 0.5rem 0 1.5rem;",
    htmltools::tags$a(href = report_download_href(path), download = basename(path), paste0(label, ": ", basename(path)))
  )
}

widget_iframe <- function(path, height = "560px") {
  htmltools::tags$iframe(
    src = report_asset_href(path),
    style = paste("width: 100%; border: 1px solid #D8D8D8; height:", height, ";")
  )
}

sanitize_report_label <- function(x) {
  gsub("[^A-Za-z0-9._-]+", "_", trimws(as.character(x)))
}

build_global_config <- function(cfg, samples, authors = "", ...) {
  dots <- list(...)
  list(
    project_name = dots$project_name %||% "",
    authors = authors,
    cfg = cfg,
    samples = samples,
    overview_samples = dots$overview_samples %||% NULL,
    use_batch_corrected = parse_bool(cfg$batch_correction$enabled, default = TRUE),
    dmp_alpha = 0.05,
    delta_beta_min = 0.10,
    dmp_use_m_values = TRUE,
    dmp_adjust_method = "BH",
    dmr_enabled = parse_bool(cfg$dmr$enabled, default = TRUE),
    enrichment_enabled = parse_bool(cfg$enrichment$enabled, default = TRUE),
    drilldown = list(
      cpg_ids = config_chr_vector(cfg$drilldown$cpg_ids),
      loci = config_chr_vector(cfg$drilldown$loci),
      genes = config_chr_vector(cfg$drilldown$genes),
      max_cpgs_per_locus = as.integer(cfg$drilldown$max_cpgs_per_locus %||% 200),
      heatmap_top_var = as.integer(cfg$drilldown$heatmap_top_var %||% 100)
    ),
    covariates = character(0)
  )
}

default_comparisons_from_samples <- function(samples) {
  active <- samples %>% dplyr::filter(parse_bool_vec(.data$include, default = TRUE))
  groups <- unique(stats::na.omit(active$group))
  if (length(groups) != 2) return(list())
  list(list(
    name = paste0(groups[[1]], "_vs_", groups[[2]]),
    target_group = groups[[1]],
    base_group = groups[[2]]
  ))
}

normalize_comparison_configs <- function(global_config, comparisons) {
  if (length(comparisons) == 0) return(list())
  normalized <- vector("list", length(comparisons))
  base_samples <- global_config$samples
  for (i in seq_along(comparisons)) {
    cmp <- comparisons[[i]]
    if (is.null(cmp$target_group) || is.null(cmp$base_group)) {
      log_error("Each comparison must define target_group and base_group")
    }
    label <- cmp$name %||% paste0(cmp$target_group, "_vs_", cmp$base_group)
    cmp_samples <- cmp$samples %||% base_samples
    if (!is.data.frame(cmp_samples)) log_error("comparison$samples must be a data.frame when provided")
    if (!("sample_id" %in% names(cmp_samples))) log_error("comparison sample table must contain sample_id")
    if (!("group" %in% names(cmp_samples))) log_error("comparison sample table must contain group")
    cmp_samples <- tibble::as_tibble(cmp_samples)
    cmp_samples <- cmp_samples %>% dplyr::filter(parse_bool_vec(.data$include, default = TRUE))
    cmp_samples <- cmp_samples %>% dplyr::filter(.data$group %in% c(cmp$base_group, cmp$target_group))
    merged_cfg <- global_config
    for (nm in setdiff(names(cmp), c("samples", "drilldown", "covariates"))) {
      merged_cfg[[nm]] <- cmp[[nm]]
    }
    merged_cfg$name <- label
    merged_cfg$samples <- cmp_samples
    merged_cfg$comparison_id <- sanitize_report_label(label)
    merged_cfg$covariates <- unique(as.character(cmp$covariates %||% global_config$covariates %||% character(0)))
    merged_cfg$dmp_alpha <- cmp$dmp_alpha %||% global_config$dmp_alpha
    merged_cfg$delta_beta_min <- cmp$delta_beta_min %||% global_config$delta_beta_min
    merged_cfg$dmp_adjust_method <- cmp$dmp_adjust_method %||% global_config$dmp_adjust_method
    merged_cfg$dmp_use_m_values <- cmp$dmp_use_m_values %||% global_config$dmp_use_m_values
    merged_cfg$use_batch_corrected <- cmp$use_batch_corrected %||% global_config$use_batch_corrected
    merged_cfg$dmr_enabled <- cmp$dmr_enabled %||% global_config$dmr_enabled
    merged_cfg$enrichment_enabled <- cmp$enrichment_enabled %||% global_config$enrichment_enabled
    merged_cfg$drilldown <- modifyList(global_config$drilldown %||% list(), cmp$drilldown %||% list())
    normalized[[i]] <- merged_cfg
  }
  normalized
}

write_comparison_index <- function(comparison_configs) {
  if (length(comparison_configs) == 0) {
    write_table(tibble::tibble(note = "No comparisons defined in DNAm_constructor.R"), "results/tables/comparison_index.csv")
    return(invisible(NULL))
  }
  idx_tbl <- dplyr::bind_rows(lapply(seq_along(comparison_configs), function(i) {
    cmp <- comparison_configs[[i]]
    tibble::tibble(
      report_order = i + 3,
      report_file = sprintf("%02d_%s.html", i + 3, sanitize_report_label(cmp$name)),
      comparison_id = cmp$comparison_id,
      comparison_name = cmp$name,
      target_group = cmp$target_group,
      base_group = cmp$base_group,
      n_samples = nrow(cmp$samples)
    )
  }))
  write_table(idx_tbl, "results/tables/comparison_index.csv")
  invisible(idx_tbl)
}

prepare_methylation_study <- function(cfg, samples) {
  ensure_dirs(".")
  validate_workspace(cfg, samples)

  datasets <- datasets_to_tibble(cfg) %>% dplyr::filter(.data$enabled)
  active_samples <- samples %>% dplyr::filter(parse_bool_vec(.data$include, default = TRUE))
  processed <- unlist(lapply(seq_len(nrow(datasets)), function(i) preprocess_single_dataset(datasets[i, , drop = FALSE], active_samples, cfg)), recursive = FALSE)
  processed <- Filter(Negate(is.null), processed)
  if (length(processed) == 0) log_error("No datasets were successfully preprocessed")

  qc_tables <- dplyr::bind_rows(lapply(processed, `[[`, "qc_table"))
  write_table(qc_tables, "results/tables/qc_metrics.csv")
  filter_summary <- dplyr::bind_rows(lapply(processed, function(x) tibble::tibble(dataset_id = x$dataset_id, import_group = x$import_group %||% x$dataset_id, !!!x$removed)))
  write_table(filter_summary, "results/tables/filter_summary.csv")

  combined <- combine_processed_datasets(processed, cfg)
  write_table(combined$run_summary, "results/tables/input_run_summary.csv")
  write_table(combined$sample_data, "results/tables/sample_inventory.csv")
  save_rds(combined, "results/rds/combined_raw.rds")

  compute_embeddings(combined$beta, combined$sample_data, "raw_all_samples", cfg)
  combined <- apply_batch_correction(combined, cfg)
  batch_tbl <- tibble::tibble(
    metric = c("enabled", "method", "batch_column", "preserve_columns"),
    value = c(
      as.character(combined$batch_correction$enabled %||% FALSE),
      coalesce_chr(combined$batch_correction$method, NA_character_),
      coalesce_chr(combined$batch_correction$batch_column, NA_character_),
      paste(combined$batch_correction$preserve_columns %||% character(0), collapse = ", ")
    )
  )
  write_table(batch_tbl, "results/tables/batch_correction_summary.csv")
  if (isTRUE(combined$batch_correction$enabled)) {
    compute_embeddings(combined$beta_active, combined$sample_data, "corrected_all_samples", cfg)
  }
  save_rds(combined, "results/rds/combined_active.rds")
  combined
}

prepare_named_subset_outputs <- function(obj, subset_samples, cfg, sample_inventory_csv, group_counts_csv, raw_prefix, corrected_prefix) {
  if (is.null(subset_samples) || !is.data.frame(subset_samples) || nrow(subset_samples) == 0) {
    return(invisible(NULL))
  }
  subset_tbl <- tibble::as_tibble(subset_samples) %>%
    dplyr::filter(parse_bool_vec(.data$include, default = TRUE))
  if (!nrow(subset_tbl)) return(invisible(NULL))
  keep_ids <- intersect(subset_tbl$sample_id, obj$sample_data$sample_id)
  if (!length(keep_ids)) return(invisible(NULL))
  subset_tbl <- subset_tbl %>%
    dplyr::filter(.data$sample_id %in% keep_ids)
  meta <- obj$sample_data %>%
    dplyr::filter(.data$sample_id %in% keep_ids)
  override_groups <- stats::setNames(as.character(subset_tbl$group), subset_tbl$sample_id)
  matched_groups <- unname(override_groups[meta$sample_id])
  keep_original <- is.na(matched_groups) | matched_groups == ""
  if (any(!keep_original)) {
    meta$group[!keep_original] <- matched_groups[!keep_original]
  }
  meta <- meta[match(subset_tbl$sample_id, meta$sample_id), , drop = FALSE]
  meta <- meta[!is.na(meta$sample_id), , drop = FALSE]
  if (!nrow(meta)) return(invisible(NULL))

  write_table(meta, sample_inventory_csv)
  group_counts <- meta %>%
    dplyr::count(.data$group, name = "n_samples") %>%
    dplyr::arrange(dplyr::desc(.data$n_samples), .data$group)
  write_table(group_counts, group_counts_csv)

  raw_beta <- obj$beta[, meta$sample_id, drop = FALSE]
  compute_embeddings(raw_beta, meta, raw_prefix, cfg)
  if (!is.null(obj$beta_active)) {
    corrected_beta <- obj$beta_active[, meta$sample_id, drop = FALSE]
    compute_embeddings(corrected_beta, meta, corrected_prefix, cfg)
  }
  invisible(meta)
}

prepare_overview_outputs <- function(obj, overview_samples, cfg) {
  prepare_named_subset_outputs(
    obj = obj,
    subset_samples = overview_samples,
    cfg = cfg,
    sample_inventory_csv = "results/tables/sample_inventory_overview.csv",
    group_counts_csv = "results/tables/overview_group_counts.csv",
    raw_prefix = "overview_cohort_raw",
    corrected_prefix = "overview_cohort_corrected"
  )
}

get_analysis_matrices <- function(obj, comparison_config) {
  use_corrected <- isTRUE(comparison_config$use_batch_corrected) && !is.null(obj$m_active)
  list(
    beta = if (use_corrected) obj$beta_active else obj$beta,
    m = if (use_corrected) obj$m_active else obj$m
  )
}

match_comparison_samples <- function(obj, comparison_config) {
  meta <- obj$sample_data
  keep_ids <- comparison_config$samples$sample_id
  meta2 <- meta[meta$sample_id %in% keep_ids, , drop = FALSE]
  meta2 <- meta2[match(keep_ids, meta2$sample_id), , drop = FALSE]
  meta2 <- meta2[!is.na(meta2$sample_id), , drop = FALSE]
  override_groups <- stats::setNames(as.character(comparison_config$samples$group), comparison_config$samples$sample_id)
  matched_groups <- unname(override_groups[meta2$sample_id])
  keep_original <- is.na(matched_groups) | matched_groups == ""
  if (any(!keep_original)) {
    meta2$group[!keep_original] <- matched_groups[!keep_original]
  }
  meta2 <- meta2 %>% dplyr::filter(.data$group %in% c(comparison_config$base_group, comparison_config$target_group))
  if (nrow(meta2) == 0) log_error("No samples remain for comparison", comparison_config$name)
  meta2
}

run_single_dmp <- function(obj, comparison_config, prefix) {
  mats <- get_analysis_matrices(obj, comparison_config)
  meta2 <- match_comparison_samples(obj, comparison_config)
  meta2$group <- factor(meta2$group, levels = c(comparison_config$base_group, comparison_config$target_group))
  counts <- table(meta2$group)
  if (as.integer(counts[[comparison_config$base_group]]) < 2 || as.integer(counts[[comparison_config$target_group]]) < 2) {
    log_error("Comparison", comparison_config$name, "requires at least two samples per group")
  }
  sample_ids <- meta2$sample_id
  mat_beta <- mats$beta[, sample_ids, drop = FALSE]
  mat_model <- if (isTRUE(comparison_config$dmp_use_m_values)) mats$m[, sample_ids, drop = FALSE] else mat_beta
  covars <- intersect(comparison_config$covariates, names(meta2))
  design <- model.matrix(stats::as.formula(paste("~", paste(c("group", covars), collapse = " + "))), data = meta2)
  fit <- limma::lmFit(mat_model, design)
  fit <- limma::eBayes(fit)
  coef_name <- colnames(design)[grepl("^group", colnames(design))][1]
  if (is.na(coef_name) || !nzchar(coef_name)) log_error("Could not determine limma group coefficient for", comparison_config$name)
  res <- limma::topTable(fit, coef = coef_name, number = Inf, sort.by = "P", adjust.method = comparison_config$dmp_adjust_method)
  res$CpG <- rownames(res)
  res$delta_beta <- rowMeans(mat_beta[, meta2$group == comparison_config$target_group, drop = FALSE], na.rm = TRUE) -
    rowMeans(mat_beta[, meta2$group == comparison_config$base_group, drop = FALSE], na.rm = TRUE)
  res <- tibble::as_tibble(res) %>% dplyr::left_join(obj$annotation, by = c("CpG" = "Name"))
  res <- res %>%
    dplyr::mutate(
      comparison_id = comparison_config$comparison_id,
      comparison_name = comparison_config$name,
      target_group = comparison_config$target_group,
      base_group = comparison_config$base_group,
      significant = adj.P.Val <= comparison_config$dmp_alpha & abs(delta_beta) >= comparison_config$delta_beta_min,
      direction = dplyr::case_when(
        significant & delta_beta >= comparison_config$delta_beta_min ~ "target_hypermethylated",
        significant & delta_beta <= -comparison_config$delta_beta_min ~ "target_hypomethylated",
        TRUE ~ "not_significant"
      ),
      CpG_base = sub("_[A-Za-z]+[0-9]+$", "", .data$CpG)
    )

  dmp_csv <- file.path("results/tables", paste0(prefix, "_dmp_table.csv"))
  dmp_sig_csv <- file.path("results/tables", paste0(prefix, "_dmp_significant.csv"))
  manifest_csv <- file.path("results/tables", paste0(prefix, "_sample_manifest.csv"))
  volcano_png <- file.path("results/figures", paste0(prefix, "_dmp_volcano.png"))
  write_table(res, dmp_csv)
  write_table(dplyr::filter(res, .data$significant), dmp_sig_csv)
  write_table(meta2, manifest_csv)
  save_plot(
    build_dmp_volcano_plot(res, comparison_config$name, comparison_config$base_group, comparison_config$target_group, comparison_config$dmp_alpha, comparison_config$delta_beta_min),
    volcano_png,
    width = 8.6,
    height = 5.8
  )
  list(
    meta = meta2,
    table = res,
    summary = tibble::tibble(
      comparison_id = comparison_config$comparison_id,
      comparison_name = comparison_config$name,
      target_group = comparison_config$target_group,
      base_group = comparison_config$base_group,
      n_target = as.integer(counts[[comparison_config$target_group]]),
      n_base = as.integer(counts[[comparison_config$base_group]]),
      n_total = nrow(meta2),
      n_sig_cpg = sum(res$significant, na.rm = TRUE),
      n_target_hyper = sum(res$direction == "target_hypermethylated", na.rm = TRUE),
      n_target_hypo = sum(res$direction == "target_hypomethylated", na.rm = TRUE)
    ),
    artifacts = list(dmp_csv = dmp_csv, dmp_sig_csv = dmp_sig_csv, manifest_csv = manifest_csv, volcano_png = volcano_png)
  )
}

run_single_embeddings <- function(obj, comparison_config, prefix) {
  mats <- get_analysis_matrices(obj, comparison_config)
  meta2 <- match_comparison_samples(obj, comparison_config)
  if (nrow(meta2) < 4) return(NULL)
  emb_prefix <- paste0(prefix, "_comparison")
  beta2 <- mats$beta[, meta2$sample_id, drop = FALSE]
  compute_embeddings(beta2, meta2, emb_prefix, comparison_config$cfg)
  artifacts <- list(
    pca_csv = file.path("results/tables", paste0(emb_prefix, "_pca.csv")),
    tsne_csv = file.path("results/tables", paste0(emb_prefix, "_tsne.csv")),
    pca_group_png = file.path("results/figures", paste0(emb_prefix, "_pca_group.png")),
    pca_batch_png = file.path("results/figures", paste0(emb_prefix, "_pca_batch.png")),
    tsne_group_png = file.path("results/figures", paste0(emb_prefix, "_tsne_group.png")),
    tsne_batch_png = file.path("results/figures", paste0(emb_prefix, "_tsne_batch.png"))
  )
  umap_csv <- file.path("results/tables", paste0(emb_prefix, "_umap.csv"))
  if (file.exists(umap_csv)) {
    artifacts$umap_csv <- umap_csv
    artifacts$umap_group_png <- file.path("results/figures", paste0(emb_prefix, "_umap_group.png"))
  }
  list(prefix = emb_prefix, artifacts = artifacts)
}

run_single_dmr <- function(obj, comparison_config, dmp_result, prefix) {
  if (!isTRUE(comparison_config$dmr_enabled)) return(NULL)
  mats <- get_analysis_matrices(obj, comparison_config)
  meta2 <- dmp_result$meta
  meta2$group <- factor(meta2$group, levels = c(comparison_config$base_group, comparison_config$target_group))
  covars <- intersect(comparison_config$covariates, names(meta2))
  design <- model.matrix(stats::as.formula(paste("~", paste(c("group", covars), collapse = " + "))), data = meta2)
  coef_name <- colnames(design)[grepl("^group", colnames(design))][1]
  sample_ids <- meta2$sample_id
  mat2 <- mats$m[, sample_ids, drop = FALSE]

  dmr_array_type <- resolve_dmrcate_array_type(rownames(mat2), obj$dmr_array_type)
  ensure_annotation_package_loaded(dmr_array_type, tool = "dmr")
  ann_obj <- tryCatch({
    if (identical(dmr_array_type, "EPICv2")) {
      DMRcate::cpg.annotate(
        "array",
        object = mat2,
        what = "M",
        arraytype = dmr_array_type,
        analysis.type = "differential",
        design = design,
        coef = which(colnames(design) == coef_name),
        fdr = comparison_config$cfg$dmr$fdr %||% 0.05,
        epicv2Filter = coalesce_chr(comparison_config$cfg$dmr$epicv2_filter, "mean"),
        epicv2Remap = parse_bool(comparison_config$cfg$dmr$epicv2_remap, default = TRUE)
      )
    } else {
      DMRcate::cpg.annotate(
        "array",
        object = mat2,
        what = "M",
        arraytype = dmr_array_type,
        analysis.type = "differential",
        design = design,
        coef = which(colnames(design) == coef_name),
        fdr = comparison_config$cfg$dmr$fdr %||% 0.05
      )
    }
  }, error = function(e) {
    log_warn("DMRcate cpg.annotate failed for", comparison_config$name, ":", conditionMessage(e))
    NULL
  })
  if (is.null(ann_obj)) return(NULL)
  dmr_fit <- tryCatch(DMRcate::dmrcate(ann_obj, lambda = comparison_config$cfg$dmr$lambda %||% 1000, C = comparison_config$cfg$dmr$C %||% 2), error = function(e) {
    log_warn("dmrcate failed for", comparison_config$name, ":", conditionMessage(e))
    NULL
  })
  if (is.null(dmr_fit)) return(NULL)
  ranges <- DMRcate::extractRanges(dmr_fit, genome = coalesce_chr(comparison_config$cfg$project$genome_build, "hg38"))
  dmr_tbl <- tibble::as_tibble(as.data.frame(ranges))
  if (nrow(dmr_tbl) == 0) return(NULL)
  dmr_tbl <- dmr_tbl %>%
    dplyr::mutate(
      comparison_id = comparison_config$comparison_id,
      direction = dplyr::case_when(
        meandiff >= 0 ~ "target_hypermethylated",
        TRUE ~ "target_hypomethylated"
      ),
      region_id = paste0(comparison_config$comparison_id, "_DMR", seq_len(dplyr::n()))
    )
  dmr_csv <- file.path("results/tables", paste0(prefix, "_dmr_table.csv"))
  dmr_png <- file.path("results/figures", paste0(prefix, "_dmr_ranked.png"))
  write_table(dmr_tbl, dmr_csv)
  plot_tbl <- dmr_tbl %>% dplyr::arrange(.data$HMFDR) %>% dplyr::slice_head(n = 15) %>% dplyr::mutate(region_id = factor(.data$region_id, levels = rev(.data$region_id)))
  p <- ggplot2::ggplot(plot_tbl, ggplot2::aes(x = -log10(pmax(.data$HMFDR, .Machine$double.xmin)), y = .data$region_id, fill = .data$direction)) +
    ggplot2::geom_col(width = 0.72) +
    ggplot2::scale_fill_manual(values = c(target_hypermethylated = "#B22222", target_hypomethylated = "#1F5A94")) +
    ggplot2::labs(title = comparison_config$name, subtitle = "Top DMRs ranked by -log10(HMFDR)", x = "-log10(HMFDR)", y = NULL) +
    theme_pub()
  save_plot(p, dmr_png, width = 8.6, height = 5.8)
  list(
    table = dmr_tbl,
    summary = tibble::tibble(
      comparison_id = comparison_config$comparison_id,
      comparison_name = comparison_config$name,
      n_regions = nrow(dmr_tbl),
      best_hmfdr = min(dmr_tbl$HMFDR, na.rm = TRUE),
      n_target_hyper = sum(dmr_tbl$direction == "target_hypermethylated", na.rm = TRUE),
      n_target_hypo = sum(dmr_tbl$direction == "target_hypomethylated", na.rm = TRUE)
    ),
    artifacts = list(dmr_csv = dmr_csv, dmr_png = dmr_png)
  )
}

run_single_enrichment <- function(obj, comparison_config, dmp_result, prefix) {
  if (!isTRUE(comparison_config$enrichment_enabled)) return(NULL)
  collections <- config_chr_vector(comparison_config$cfg$enrichment$collections)
  if (length(collections) == 0) collections <- c("GO", "KEGG")
  all_cpg <- unique(sub("_[A-Za-z]+[0-9]+$", "", rownames(obj$beta_active)))
  gometh_array_type <- resolve_gometh_array_type(rownames(obj$beta_active), obj$gometh_array_type)
  ensure_annotation_package_loaded(gometh_array_type, tool = "gometh")
  pieces <- list()
  for (direction in c("target_hypermethylated", "target_hypomethylated")) {
    sig <- unique(sub("_[A-Za-z]+[0-9]+$", "", dmp_result$table$CpG[dmp_result$table$direction == direction]))
    if (length(sig) < 5) next
    for (collection in collections) {
      enr <- tryCatch(
        missMethyl::gometh(sig.cpg = sig, all.cpg = all_cpg, collection = collection, array.type = gometh_array_type),
        error = function(e) {
          log_warn("gometh failed for", comparison_config$name, direction, collection, ":", conditionMessage(e))
          NULL
        }
      )
      if (is.null(enr)) next
      pieces[[paste(direction, collection, sep = "_")]] <- tibble::as_tibble(enr) %>%
        dplyr::mutate(comparison_id = comparison_config$comparison_id, direction = direction, collection = collection)
    }
  }
  if (length(pieces) == 0) return(NULL)
  enr_tbl <- dplyr::bind_rows(pieces)
  enr_csv <- file.path("results/tables", paste0(prefix, "_enrichment_summary.csv"))
  write_table(enr_tbl, enr_csv)
  list(table = enr_tbl, artifacts = list(enrichment_csv = enr_csv))
}

run_single_drilldown <- function(obj, comparison_config, prefix) {
  drill_cfg <- comparison_config$drilldown %||% list()
  if ((length(drill_cfg$cpg_ids %||% character(0)) + length(drill_cfg$loci %||% character(0)) + length(drill_cfg$genes %||% character(0))) == 0) return(NULL)
  mats <- get_analysis_matrices(obj, comparison_config)
  beta <- mats$beta
  ann <- obj$annotation
  meta <- match_comparison_samples(obj, comparison_config)
  selected <- list()
  cpg_ids <- as.character(drill_cfg$cpg_ids %||% character(0))
  if (length(cpg_ids) > 0) selected$cpgs <- match_probe_ids(cpg_ids, rownames(beta))
  genes <- as.character(drill_cfg$genes %||% character(0))
  if (length(genes) > 0) {
    gene_col <- intersect(c("UCSC_RefGene_Name", "GeneSymbol", "SYMBOL"), names(ann))[1]
    if (!is.na(gene_col) && length(gene_col) > 0) {
      selected$genes <- unique(ann$Name[vapply(strsplit(as.character(ann[[gene_col]]), ";"), function(parts) any(parts %in% genes), logical(1))])
    }
  }
  loci <- as.character(drill_cfg$loci %||% character(0))
  if (length(loci) > 0) {
    chr_col <- choose_chr_col(ann)
    pos_col <- intersect(c("pos", "Position"), names(ann))[1]
    if (!is.na(chr_col) && !is.na(pos_col)) {
      hits <- character(0)
      for (locus in loci) {
        loc_match <- stringr::str_match(locus, "^([^:]+):(\\d+)-(\\d+)$")
        if (any(is.na(loc_match))) next
        hits <- c(hits, ann$Name[ann[[chr_col]] == loc_match[, 2] & ann[[pos_col]] >= as.numeric(loc_match[, 3]) & ann[[pos_col]] <= as.numeric(loc_match[, 4])])
      }
      selected$loci <- unique(hits)
    }
  }
  drill_rows <- unique(unlist(selected))
  drill_rows <- intersect(drill_rows, rownames(beta))
  if (length(drill_rows) == 0) return(NULL)
  drill_beta <- beta[drill_rows, meta$sample_id, drop = FALSE]
  beta_csv <- file.path("results/tables", paste0(prefix, "_drilldown_beta_matrix.csv"))
  meta_csv <- file.path("results/tables", paste0(prefix, "_drilldown_sample_metadata.csv"))
  summary_csv <- file.path("results/tables", paste0(prefix, "_drilldown_summary.csv"))
  heatmap_png <- file.path("results/figures", paste0(prefix, "_drilldown_heatmap.png"))
  write_table(tibble::rownames_to_column(as.data.frame(drill_beta), "CpG"), beta_csv)
  write_table(meta, meta_csv)
  write_table(tibble::tibble(category = names(selected), n_cpg = vapply(selected, length, integer(1))), summary_csv)
  heatmap_n <- min(nrow(drill_beta), as.integer(drill_cfg$heatmap_top_var %||% 100))
  heatmap_mat <- drill_beta[seq_len(heatmap_n), , drop = FALSE]
  heatmap_mat_scaled <- t(scale(t(heatmap_mat)))
  heatmap_mat_scaled[is.na(heatmap_mat_scaled)] <- 0
  annotation_df <- data.frame(group = meta$group, batch = meta$batch, row.names = meta$sample_id, stringsAsFactors = FALSE)
  pheatmap::pheatmap(heatmap_mat_scaled, annotation_col = annotation_df, filename = heatmap_png, width = 10, height = 8)
  list(
    summary = readr::read_csv(summary_csv, show_col_types = FALSE),
    artifacts = list(beta_csv = beta_csv, meta_csv = meta_csv, summary_csv = summary_csv, heatmap_png = heatmap_png)
  )
}

write_comparison_bundle <- function(bundle, prefix) {
  bundle_path <- file.path("results/rds", paste0(prefix, "_bundle.rds"))
  save_rds(bundle, bundle_path)
  bundle_path
}

run_single_comparison_analysis <- function(obj, comparison_config, report_index) {
  prefix <- sprintf("%02d_%s", report_index, sanitize_report_label(comparison_config$name))
  embeddings <- run_single_embeddings(obj, comparison_config, prefix)
  dmp <- run_single_dmp(obj, comparison_config, prefix)
  dmr <- run_single_dmr(obj, comparison_config, dmp, prefix)
  enrichment <- run_single_enrichment(obj, comparison_config, dmp, prefix)
  drilldown <- run_single_drilldown(obj, comparison_config, prefix)
  bundle <- list(
    prefix = prefix,
    report_index = report_index,
    report_file = paste0(prefix, ".html"),
    comparison = comparison_config,
    embeddings = embeddings,
    dmp = dmp,
    dmr = dmr,
    enrichment = enrichment,
    drilldown = drilldown
  )
  bundle$bundle_path <- write_comparison_bundle(bundle, prefix)
  bundle
}

render_global_reports <- function(authors = NULL) {
  for (file in c("00_study_overview.qmd", "01_input_qc.qmd", "02_all_samples_embeddings.qmd", "03_batch_diagnostics.qmd")) {
    quarto_render_cli(file, output_dir = "reports", metadata = list(author = authors))
  }
}

render_comparison_report <- function(bundle, authors = NULL) {
  quarto_render_cli(
    "comparison_report.qmd",
    output_file = bundle$report_file,
    output_dir = "reports",
    metadata = list(author = authors, title = format_report_title(bundle$report_index, bundle$comparison$name)),
    execute_params = list(
      bundle_path = normalizePath(bundle$bundle_path, winslash = "/", mustWork = TRUE),
      report_title = format_report_title(bundle$report_index, bundle$comparison$name)
    )
  )
}

run_methylation_study <- function(global_config, comparisons = list()) {
  cfg <- global_config$cfg
  samples <- global_config$samples
  combined <- prepare_methylation_study(cfg, samples)
  prepare_overview_outputs(combined, global_config$overview_samples, cfg)
  comparison_configs <- normalize_comparison_configs(global_config, comparisons)
  write_comparison_index(comparison_configs)
  render_global_reports(authors = global_config$authors)
  if (length(comparison_configs) == 0) {
    log_info("No comparisons defined in DNAm_constructor.R; rendered only global reports.")
    return(invisible(list(combined = combined, comparisons = list())))
  }
  comparison_bundles <- lapply(seq_along(comparison_configs), function(i) {
    bundle <- run_single_comparison_analysis(combined, comparison_configs[[i]], i + 3)
    render_comparison_report(bundle, authors = global_config$authors)
    bundle
  })
  invisible(list(combined = combined, comparisons = comparison_bundles))
}

render_report_table <- function(df, preferred = NULL, page_length = 10, max_extra = 0, caption = NULL) {
  selected <- select_report_columns(df, preferred = preferred, max_extra = max_extra)
  tbl <- format_report_table(selected)
  if (requireNamespace("DT", quietly = TRUE)) {
    cap <- if (!is.null(caption) && nzchar(caption)) htmltools::tags$caption(style = "caption-side: top; text-align: left; font-weight: 600; padding-bottom: 0.5rem;", caption) else NULL
    return(DT::datatable(tbl, rownames = FALSE, caption = cap, class = "compact stripe hover", options = list(pageLength = page_length, scrollX = TRUE, autoWidth = TRUE, dom = "tip")))
  }
  knitr::kable(tbl, format = "html", caption = caption)
}
