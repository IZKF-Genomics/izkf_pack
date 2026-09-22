suppressPackageStartupMessages({
  library(readr)
  library(dplyr)
  library(tibble)
  library(htmltools)
  library(knitr)
  library(yaml)
})

read_result_table <- function(path) {
  if (!file.exists(path)) stop("Required report table not found: ", path, call. = FALSE)
  readr::read_csv(path, show_col_types = FALSE)
}

format_report_value <- function(value, name = "") {
  if (length(value) == 0 || is.na(value)) return("")
  if (!is.numeric(value)) return(as.character(value))
  lower <- tolower(name)
  if (lower %in% c("pvalue", "padj", "min_fdr")) return(formatC(value, format = "e", digits = 2))
  if (grepl("fold|conf_|fraction|correlation|lfc", lower)) return(formatC(value, format = "f", digits = 3))
  format(value, big.mark = ",", trim = TRUE, scientific = FALSE)
}

render_report_table <- function(df, columns = NULL, max_rows = 20, caption = NULL) {
  if (!is.null(columns)) df <- df[, intersect(columns, names(df)), drop = FALSE]
  preview <- head(df, max_rows)
  for (name in names(preview)) {
    preview[[name]] <- vapply(preview[[name]], format_report_value, character(1), name = name)
  }
  html <- knitr::kable(preview, format = "html", escape = TRUE, caption = caption, table.attr = 'class="report-table"')
  note <- if (nrow(df) > max_rows) sprintf("<p class='table-note'>Showing %d of %d rows. Download the complete CSV for all results.</p>", max_rows, nrow(df)) else ""
  htmltools::HTML(paste0("<div class='report-table-wrap'>", html, "</div>", note))
}

metric_cards <- function(items) {
  cards <- lapply(items, function(item) {
    tags$div(class = "metric-card", tags$div(class = "metric-value", item$value), tags$div(class = "metric-label", item$label))
  })
  tags$div(class = "metric-grid", cards)
}

interpretation_box <- function(title, text, kind = "read") {
  tags$div(class = paste("interpretation-box", paste0("interpretation-", kind)), tags$strong(title), tags$p(text))
}

download_links <- function(paths) {
  links <- lapply(paths, function(path) tags$a(class = "asset-link", href = path, download = basename(path), basename(path)))
  tags$div(class = "asset-links", links)
}

evidence_summary_text <- function(row, alpha, lfc_threshold) {
  if (row$n_evidence_threshold > 0) {
    sprintf(
      "%d miRNAs met both FDR < %.3g and |shrunken log2FC| ≥ %.2f; %d met the FDR criterion alone.",
      row$n_evidence_threshold, alpha, lfc_threshold, row$n_fdr_significant
    )
  } else if (row$n_fdr_significant > 0) {
    sprintf(
      "%d miRNAs met FDR < %.3g, but none also reached |shrunken log2FC| ≥ %.2f. Effect magnitude should therefore remain central to interpretation.",
      row$n_fdr_significant, alpha, lfc_threshold
    )
  } else {
    sprintf(
      "No miRNA reached FDR < %.3g. This means the prespecified evidence threshold was not crossed; it does not demonstrate absence of biological change.",
      alpha
    )
  }
}

contrast_direction_text <- function(contrast) {
  if (contrast$type == "interaction") {
    sprintf("Positive values mean that the %s-to-%s change is more positive in %s than in %s.", contrast$base_time, contrast$target_time, contrast$target_group, contrast$base_group)
  } else if (contrast$type == "paired_time") {
    sprintf("Positive values mean higher expression at %s than at %s within %s.", contrast$target_time, contrast$base_time, contrast$group)
  } else {
    sprintf("Positive values mean higher expression in %s than in %s at %s.", contrast$target_group, contrast$base_group, contrast$at_time)
  }
}

contrast_biological_question <- function(contrast) {
  if (contrast$type == "interaction") {
    sprintf(
      "Did the change from %s to %s differ between %s and %s?",
      contrast$base_time, contrast$target_time, contrast$target_group, contrast$base_group
    )
  } else if (contrast$type == "paired_time") {
    sprintf(
      "Which miRNAs changed from %s to %s within the %s animals?",
      contrast$base_time, contrast$target_time, contrast$group
    )
  } else {
    sprintf(
      "Which miRNAs differed between %s and %s at %s?",
      contrast$target_group, contrast$base_group, contrast$at_time
    )
  }
}

contrast_role_text <- function(contrast, primary_id) {
  if (contrast$id == primary_id) {
    "Primary comparison: this directly tests whether the two groups followed different trajectories over time."
  } else if (contrast$type == "two_group") {
    "Endpoint comparison: this describes the groups at the final time point but does not by itself show that their changes over time differed."
  } else {
    "Within-group comparison: this describes change over time in one group but does not by itself establish a difference between groups."
  }
}

contrast_result_text <- function(row, result, alpha, lfc_threshold) {
  hits <- result |> filter(evidence_threshold %in% TRUE)
  if (nrow(hits) == 0) {
    return(sprintf(
      "No miRNA met both FDR < %.3g and |shrunken log2FC| ≥ %.2f.",
      alpha, lfc_threshold
    ))
  }
  ids <- paste(head(hits$mirna_id, 6), collapse = ", ")
  suffix <- if (nrow(hits) > 6) sprintf(", and %d more", nrow(hits) - 6) else ""
  sprintf(
    "%d miRNA%s met both criteria: %s%s.",
    nrow(hits), ifelse(nrow(hits) == 1, "", "s"), ids, suffix
  )
}

contrast_caution_text <- function(contrast) {
  if (contrast$type == "interaction") {
    "A non-significant interaction does not prove identical biology; it means this dataset did not resolve a group-specific difference in change at the prespecified threshold."
  } else if (contrast$type == "two_group") {
    "An endpoint difference can reflect a baseline difference, a change over time, or both. Interpret it together with the interaction and paired comparisons."
  } else {
    "A change within one group is not evidence that this group changed more than the other group. That claim requires the interaction comparison."
  }
}
