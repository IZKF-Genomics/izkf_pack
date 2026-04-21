suppressPackageStartupMessages({
  library(readr)
  library(dplyr)
  library(tibble)
})

parse_args <- function(args) {
  out <- list(from = NULL, only = NULL, no_render = FALSE)
  i <- 1L
  while (i <= length(args)) {
    arg <- args[[i]]
    if (identical(arg, "--from")) {
      i <- i + 1L
      if (i > length(args)) stop("--from requires an integer report order", call. = FALSE)
      out$from <- as.integer(args[[i]])
    } else if (identical(arg, "--only")) {
      i <- i + 1L
      if (i > length(args)) stop("--only requires a comma-separated list of report orders", call. = FALSE)
      vals <- trimws(unlist(strsplit(args[[i]], ",")))
      out$only <- as.integer(vals[nzchar(vals)])
    } else if (identical(arg, "--no-render")) {
      out$no_render <- TRUE
    } else if (identical(arg, "--help")) {
      cat(
        "Usage:\n",
        "  Rscript rerun_failed_comparisons.R --from 4\n",
        "  Rscript rerun_failed_comparisons.R --only 4,5,8\n",
        "Options:\n",
        "  --from <int>      Rerun comparisons starting at report order N (e.g. 4)\n",
        "  --only <list>     Rerun only these report orders, comma-separated\n",
        "  --no-render       Recompute bundles/tables only, skip Quarto rendering\n",
        sep = ""
      )
      quit(save = "no", status = 0)
    } else {
      stop("Unknown argument: ", arg, call. = FALSE)
    }
    i <- i + 1L
  }
  if (!is.null(out$from) && !is.null(out$only)) {
    stop("Use either --from or --only, not both", call. = FALSE)
  }
  if (is.null(out$from) && is.null(out$only)) {
    out$from <- 4L
  }
  out
}

args <- parse_args(commandArgs(trailingOnly = TRUE))

Sys.setenv(DNAM_SKIP_RUN = "1")
source("DNAm_constructor.R")

if (!file.exists("results/rds/combined_active.rds")) {
  stop("Missing cached combined object: results/rds/combined_active.rds", call. = FALSE)
}

validate_workspace(cfg, samples)
combined <- readRDS("results/rds/combined_active.rds")
comparison_configs <- normalize_comparison_configs(global_config, comparisons)

if (length(comparison_configs) == 0) {
  stop("No comparisons defined in DNAm_constructor.R", call. = FALSE)
}

comparison_index <- tibble::tibble(
  report_order = seq_along(comparison_configs) + 3L,
  comparison_idx = seq_along(comparison_configs),
  comparison_name = vapply(comparison_configs, function(x) x$name, character(1)),
  report_file = sprintf("%02d_%s.html", seq_along(comparison_configs) + 3L, vapply(comparison_configs, function(x) sanitize_report_label(x$name), character(1)))
)

selected <- if (!is.null(args$only)) {
  comparison_index %>% dplyr::filter(.data$report_order %in% args$only)
} else {
  comparison_index %>% dplyr::filter(.data$report_order >= args$from)
}

if (nrow(selected) == 0) {
  stop("No comparison reports matched the requested selection", call. = FALSE)
}

message("Rerunning comparison reports: ", paste(selected$report_order, collapse = ", "))

for (k in seq_len(nrow(selected))) {
  report_order <- selected$report_order[[k]]
  cmp_idx <- selected$comparison_idx[[k]]
  cfg_cmp <- comparison_configs[[cmp_idx]]
  bundle <- run_single_comparison_analysis(combined, cfg_cmp, report_order)
  if (!isTRUE(args$no_render)) {
    render_comparison_report(bundle, authors = global_config$authors)
  }
  message("Finished report order ", report_order, ": ", cfg_cmp$name)
}

message("Done.")
