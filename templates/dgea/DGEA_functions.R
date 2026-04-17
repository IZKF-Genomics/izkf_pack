`%||%` <- function(x, y) if (is.null(x) || (is.character(x) && identical(x, ""))) y else x
null_if_na <- function(x) {
  if (is.null(x)) {
    return(NULL)
  }
  if (length(x) == 1 && is.na(x)) {
    return(NULL)
  }
  x
}

yaml_escape_string <- function(x) {
  gsub("\"", "\\\\\"", x)
}

yaml_format_value <- function(x) {
  if (is.null(x) || (length(x) == 1 && is.na(x))) {
    return("null")
  }
  if (inherits(x, "formula")) {
    return(paste(as.character(x), collapse = " "))
  }
  if (is.logical(x) || is.numeric(x)) {
    return(as.character(x))
  }
  if (is.character(x)) {
    if (length(x) == 1) {
      return(paste0("\"", yaml_escape_string(x), "\""))
    }
    if (length(x) == 0) {
      return("[]")
    }
    vals <- vapply(x, function(v) paste0("\"", yaml_escape_string(v), "\""), character(1))
    return(paste0("[", paste(vals, collapse = ", "), "]"))
  }
  paste0("\"", yaml_escape_string(as.character(x)), "\"")
}

write_qmd_with_params <- function(template_path, output_path, params) {
  lines <- readLines(template_path, warn = FALSE)
  header_start <- which(lines == "---")[1]
  header_end <- which(lines == "---")[2]
  if (is.na(header_start) || is.na(header_end)) {
    stop("QMD template must contain a YAML header delimited by '---'.")
  }

  header <- lines[(header_start + 1):(header_end - 1)]
  params_idx <- which(grepl("^params:\\s*$", header))
  if (length(params_idx) > 0) {
    header <- header[seq_len(params_idx[1] - 1)]
  }

  params_block <- c(
    "params:",
    paste0("  ", names(params), ": ", vapply(params, yaml_format_value, character(1)))
  )

  new_lines <- c(
    lines[1:header_start],
    header,
    params_block,
    lines[header_end:length(lines)]
  )
  writeLines(new_lines, output_path)
  invisible(output_path)
}

stage_render_support_files <- function(workspace_dir, results_dir) {
  support_files <- c("references.bib", "thermofisher_LSG_manuals_cms_095046.txt")
  for (name in support_files) {
    src <- file.path(workspace_dir, name)
    dest <- file.path(results_dir, name)
    if (file.exists(src) && !file.exists(dest)) {
      file.copy(src, dest, overwrite = FALSE)
    }
  }
}

render_quarto_in_results <- function(qmd_path, output_file, results_dir) {
  old_wd <- getwd()
  on.exit(setwd(old_wd), add = TRUE)
  setwd(results_dir)
  quarto::quarto_render(
    input = basename(qmd_path),
    output_file = output_file,
    quiet = TRUE
  )
  misplaced_output <- file.path(old_wd, output_file)
  expected_output <- file.path(results_dir, output_file)
  if (file.exists(misplaced_output) && normalizePath(misplaced_output, winslash = "/", mustWork = FALSE) !=
      normalizePath(expected_output, winslash = "/", mustWork = FALSE)) {
    file.rename(misplaced_output, expected_output)
  }
}

####################################################################
# Render DGEA reports (no hidden RData; pass params explicitly)
####################################################################

render_DGEA_report <- function(config) {
  stopifnot(!is.null(config$base_group), !is.null(config$target_group))
  results_dir <- config$results_dir %||% file.path(getwd(), "results")
  workspace_dir <- config$workspace_dir %||% getwd()
  dir.create(results_dir, recursive = TRUE, showWarnings = FALSE)
  stage_render_support_files(workspace_dir, results_dir)

  filetag <- if (!is.null(config$additional_tag) &&
                  nzchar(config$additional_tag)) {
    paste0(config$target_group, "_vs_", config$base_group, "_", config$additional_tag)
  } else {
    paste0(config$target_group, "_vs_", config$base_group)
  }

  csv_path <- file.path(results_dir, paste0("DGEA_", filetag, "_samplesheet.csv"))
  config$samplesheet <- config$samplesheet[config$samplesheet$group %in% c(config$base_group, config$target_group),]
  utils::write.csv(config$samplesheet, csv_path, row.names = FALSE)
      
  execute_params <- list(
    salmon_dir = config$salmon_dir,
    samplesheet_path = csv_path,
    organism = config$organism,
    spikein = config$spikein,
    application = config$application,
    name = config$name %||% "project",
    authors = config$authors %||% "PROJECT_AUTHORS",
    base_group = config$base_group,
    target_group = config$target_group,
    additional_tag = null_if_na(config$additional_tag),
    design_formula = if (inherits(config$design_formula, "formula")) {
      paste(as.character(config$design_formula), collapse = " ")
    } else {
      config$design_formula
    },
    paired = isTRUE(config$paired),
    go = isTRUE(config$go),
    gsea = isTRUE(config$gsea),
    cutoff_adj_p = config$cutoff_adj_p %||% 0.05,
    cutoff_log2fc = config$cutoff_log2fc %||% 1,
    pvalueCutoff_GO = config$pvalueCutoff_GO %||% 0.05,
    pvalueCutoff_GSEA = config$pvalueCutoff_GSEA %||% 0.05,
    highlighted_genes = null_if_na(config$highlighted_genes),
    tx2gene_file = config$tx2gene_file %||% file.path(config$salmon_dir, "tx2gene.tsv"),
    filetag = filetag
  )

  qmd_file <- paste0("DGEA_", filetag, ".qmd")
  qmd_path <- file.path(results_dir, qmd_file)
  write_qmd_with_params(
    template_path = file.path(workspace_dir, "DGEA_template.qmd"),
    output_path = qmd_path,
    params = execute_params
  )
  message("Writing standalone QMD to: ", normalizePath(qmd_path, winslash = "/", mustWork = FALSE))

  output_file <- paste0("DGEA_", filetag, ".html")
  output_path <- file.path(results_dir, output_file)
  message("Rendering DGEA report to: ", normalizePath(output_path, winslash = "/", mustWork = FALSE))
  render_quarto_in_results(qmd_path, output_file, results_dir)
  invisible(output_path)
}

render_DGEA_all_sample <- function(config) {
  results_dir <- config$results_dir %||% file.path(getwd(), "results")
  workspace_dir <- config$workspace_dir %||% getwd()
  dir.create(results_dir, recursive = TRUE, showWarnings = FALSE)
  stage_render_support_files(workspace_dir, results_dir)

  csv_path <- file.path(results_dir, "DGEA_all_samplesheet.csv")
  utils::write.csv(config$samplesheet, csv_path, row.names = FALSE)

  execute_params <- list(
    salmon_dir = config$salmon_dir,
    samplesheet_path = csv_path,
    organism = config$organism,
    spikein = config$spikein,
    application = config$application,
    name = config$name %||% "project",
    authors = config$authors %||% "PROJECT_AUTHORS"
  )

  qmd_file <- "DGEA_all_samples.qmd"
  qmd_path <- file.path(results_dir, qmd_file)
  write_qmd_with_params(
    template_path = file.path(workspace_dir, "DGEA_all_samples.qmd"),
    output_path = qmd_path,
    params = execute_params
  )
  message("Writing standalone QMD to: ", normalizePath(qmd_path, winslash = "/", mustWork = FALSE))

  output_file <- "DGEA_all_samples.html"
  output_path <- file.path(results_dir, output_file)
  message("Rendering DGEA all-samples report to: ", normalizePath(output_path, winslash = "/", mustWork = FALSE))
  render_quarto_in_results(qmd_path, output_file, results_dir)
  invisible(output_path)
}

####################################################################
# Optional: Simple comparison report (parameterised, no temp files)
####################################################################

render_simple_report <- function(config) {
  stopifnot(!is.null(config$sample1), !is.null(config$sample2))
  results_dir <- config$results_dir %||% file.path(getwd(), "results")
  workspace_dir <- config$workspace_dir %||% getwd()
  dir.create(results_dir, recursive = TRUE, showWarnings = FALSE)
  stage_render_support_files(workspace_dir, results_dir)

  filetag <- paste0(config$sample2, "_vs_", config$sample1)
  execute_params <- list(
    salmon_dir = config$salmon_dir,
    samplesheet = config$samplesheet,
    organism = config$organism,
    spikein = config$spikein,
    application = config$application,
    name = config$name %||% "project",
    authors = config$authors %||% "PROJECT_AUTHORS",
    sample1 = config$sample1,
    sample2 = config$sample2,
    filetag = filetag
  )

  qmd_file <- paste0("SimpleComparison_", filetag, ".qmd")
  qmd_path <- file.path(results_dir, qmd_file)
  write_qmd_with_params(
    template_path = file.path(workspace_dir, "SimpleComparison_template.qmd"),
    output_path = qmd_path,
    params = execute_params
  )
  message("Writing standalone QMD to: ", normalizePath(qmd_path, winslash = "/", mustWork = FALSE))

  output_file <- paste0("SimpleComparison_", filetag, ".html")
  output_path <- file.path(results_dir, output_file)
  message("Rendering simple comparison report to: ", normalizePath(output_path, winslash = "/", mustWork = FALSE))
  render_quarto_in_results(qmd_path, output_file, results_dir)
  invisible(output_path)
}

####################################################################
# Utility functions for integrity checks
####################################################################

check_missing_dirs <- function(paths) {
  if (!is.character(paths)) {
    stop("`paths` must be a character vector.")
  }

  missing_dirs <- paths[!vapply(paths, dir.exists, logical(1))]

  if (length(missing_dirs) > 0) {
    message("⚠️ The following directories are missing:")
    for (d in missing_dirs) {
      message("  - ", d)
    }
  } else {
    message("✅ All directories exist.")
  }

  invisible(missing_dirs)
}
