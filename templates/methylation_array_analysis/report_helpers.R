suppressPackageStartupMessages({
  library(RcppTOML)
  library(readr)
  library(dplyr)
  library(tibble)
  library(ggplot2)
  library(htmltools)
  library(knitr)
})

`%||%` <- function(x, y) if (is.null(x)) y else x

coalesce_chr <- function(x, default = "") {
  if (is.null(x) || length(x) == 0 || is.na(x)) return(default)
  as.character(x[[1]])
}

load_project_config <- function(path = "config/datasets.toml") {
  if (!file.exists(path)) stop("Config not found: ", path, call. = FALSE)
  RcppTOML::parseTOML(path)
}

write_table <- function(df, path) {
  dir.create(dirname(path), recursive = TRUE, showWarnings = FALSE)
  readr::write_csv(as_tibble(df), path)
  invisible(path)
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

drop_empty_report_columns <- function(df) {
  tbl <- as.data.frame(df, stringsAsFactors = FALSE)
  if (ncol(tbl) == 0) return(tbl)
  keep <- vapply(tbl, function(col) {
    vals <- col
    if (is.factor(vals)) vals <- as.character(vals)
    vals <- vals[!is.na(vals)]
    if (length(vals) == 0) return(FALSE)
    vals_chr <- trimws(as.character(vals))
    any(nzchar(vals_chr) & vals_chr != "NA")
  }, logical(1))
  tbl[, keep, drop = FALSE]
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

report_image <- function(path, alt = NULL, max_width = "100%") {
  htmltools::tags$img(
    src = report_asset_href(path),
    alt = alt %||% basename(as.character(path[[1]])),
    style = paste0("display:block; width:100%; max-width:", max_width, "; height:auto; margin:0.75rem 0 1.25rem;")
  )
}

widget_iframe <- function(path, height = "560px") {
  src_path <- as.character(path[[1]])
  htmltools::tags$iframe(
    src = src_path,
    scrolling = "no",
    style = paste("width: 100%; border: 1px solid #D8D8D8; height:", height, "; overflow: hidden;")
  )
}

preview_report_table <- function(df, max_rows_inline = 50) {
  if (is.null(df)) return(df)
  if (nrow(df) <= max_rows_inline) return(df)
  utils::head(df, max_rows_inline)
}

report_preview_note <- function(df, max_rows_inline = 50, noun = "rows") {
  if (is.null(df) || nrow(df) <= max_rows_inline) return(NULL)
  htmltools::tags$p(
    style = "margin: 0.35rem 0 0.9rem; color: #5B5B5B;",
    sprintf("Showing the first %d of %d %s inline. The complete table is retained in the results tables directory.", max_rows_inline, nrow(df), noun)
  )
}

render_report_table <- function(df, preferred = NULL, page_length = 10, max_extra = 0, caption = NULL, drop_empty = TRUE, wide = FALSE) {
  selected <- select_report_columns(df, preferred = preferred, max_extra = max_extra)
  tbl <- format_report_table(selected)
  if (drop_empty) tbl <- drop_empty_report_columns(tbl)
  table_id <- paste0("report-table-", paste(sample(c(letters, LETTERS, 0:9), 10, replace = TRUE), collapse = ""))
  pager_id <- paste0(table_id, "-pager")
  info_id <- paste0(table_id, "-info")
  prev_id <- paste0(table_id, "-prev")
  next_id <- paste0(table_id, "-next")
  page_num_id <- paste0(table_id, "-page")
  per_page <- if (is.null(page_length) || is.na(page_length) || page_length <= 0) 15L else min(as.integer(page_length), 15L)
  wrap_class <- if (isTRUE(wide)) "report-table-wrap report-table-wrap-wide" else "report-table-wrap"
  out <- htmltools::tagList(
    htmltools::tags$style(
      htmltools::HTML(
        "
        .report-table-wrap {
          overflow-x: auto;
          margin: 0.5rem 0 1.25rem;
        }
        .report-table-wrap.report-table-wrap-wide {
          width: 100%;
          max-width: 100%;
        }
        table.report-table {
          width: 100%;
          border-collapse: collapse;
          border-spacing: 0;
          table-layout: auto;
        }
        .report-table-wrap.report-table-wrap-wide table.report-table {
          min-width: 1200px;
        }
        table.report-table.sortable thead th {
          cursor: pointer;
          user-select: none;
          position: relative;
          padding-right: 1.2rem;
        }
        table.report-table.sortable thead th::after {
          content: '↕';
          position: absolute;
          right: 0.35rem;
          color: #9A9A9A;
          font-size: 0.82rem;
        }
        table.report-table.sortable thead th.sort-asc::after {
          content: '↑';
          color: #3A3A3A;
        }
        table.report-table.sortable thead th.sort-desc::after {
          content: '↓';
          color: #3A3A3A;
        }
        table.report-table caption {
          caption-side: top;
          text-align: left;
          font-weight: 600;
          padding-bottom: 0.5rem;
        }
        table.report-table thead th {
          text-align: left !important;
          font-weight: 700;
          border-bottom: 1px solid #B8B8B8;
          padding: 0.55rem 0.65rem;
          vertical-align: top;
          white-space: nowrap;
        }
        table.report-table tbody td {
          text-align: left !important;
          vertical-align: top;
          padding: 0.55rem 0.65rem;
          border-top: 1px solid #ECECEC;
          white-space: normal;
          word-break: break-word;
          font-variant-numeric: tabular-nums;
        }
        table.report-table tbody tr:nth-child(odd) td {
          background: #FAFAFA;
        }
        .report-table-pager {
          display: flex;
          justify-content: space-between;
          align-items: center;
          gap: 0.75rem;
          margin: -0.35rem 0 1.25rem;
          font-size: 0.95rem;
          color: #4A4A4A;
          flex-wrap: wrap;
        }
        .report-table-pager-controls {
          display: flex;
          align-items: center;
          gap: 0.5rem;
        }
        .report-table-pager button {
          border: 1px solid #CFCFCF;
          background: white;
          color: #333333;
          border-radius: 0.35rem;
          padding: 0.28rem 0.75rem;
          cursor: pointer;
        }
        .report-table-pager button:disabled {
          opacity: 0.5;
          cursor: default;
        }
        "
      )
    ),
    htmltools::tags$div(
      class = wrap_class,
      htmltools::tags$table(
        id = table_id,
        class = "report-table sortable",
        if (!is.null(caption) && nzchar(caption)) {
          htmltools::tags$caption(caption)
        },
        htmltools::tags$thead(
          htmltools::tags$tr(
            lapply(names(tbl), function(nm) htmltools::tags$th(nm))
          )
        ),
        htmltools::tags$tbody(
          lapply(seq_len(nrow(tbl)), function(i) {
            htmltools::tags$tr(
              lapply(tbl[i, , drop = FALSE], function(value) {
                htmltools::tags$td(if (is.na(value) || identical(value, "NA")) "" else as.character(value))
              })
            )
          })
        )
      )
    ),
    htmltools::tags$div(
      id = pager_id,
      class = "report-table-pager",
      htmltools::tags$div(id = info_id, "Showing 1 to 1 of 1 entries"),
      htmltools::tags$div(
        class = "report-table-pager-controls",
        htmltools::tags$button(id = prev_id, type = "button", "Previous"),
        htmltools::tags$span(id = page_num_id, "Page 1 of 1"),
        htmltools::tags$button(id = next_id, type = "button", "Next")
      )
    ),
    htmltools::tags$script(
      htmltools::HTML(
        sprintf(
          "
          (function() {
            function parseValue(text) {
              var cleaned = String(text || '').trim().replace(/,/g, '');
              if (cleaned === '') return {type: 'string', value: ''};
              if (/^[+-]?(?:\\d+\\.?\\d*|\\.\\d+)(?:e[+-]?\\d+)?$/i.test(cleaned)) {
                return {type: 'number', value: parseFloat(cleaned)};
              }
              return {type: 'string', value: cleaned.toLowerCase()};
            }
            var table = document.getElementById('%s');
            if (!table) return;
            var headers = table.querySelectorAll('thead th');
            var pager = document.getElementById('%s');
            var info = document.getElementById('%s');
            var prevBtn = document.getElementById('%s');
            var nextBtn = document.getElementById('%s');
            var pageNum = document.getElementById('%s');
            var tbody = table.tBodies[0];
            var rows = Array.prototype.slice.call(tbody.querySelectorAll('tr'));
            var perPage = %d;
            var currentPage = 1;

            function renderPage() {
              if (perPage <= 0) perPage = 15;
              var totalPages = Math.max(1, Math.ceil(rows.length / perPage));
              if (currentPage > totalPages) currentPage = totalPages;
              var start = (currentPage - 1) * perPage;
              var end = start + perPage;
              rows.forEach(function(row, idx) {
                row.style.display = (idx >= start && idx < end) ? '' : 'none';
              });
              if (pager) pager.style.display = '';
              if (info) {
                info.textContent = 'Showing ' + (start + 1) + ' to ' + Math.min(end, rows.length) + ' of ' + rows.length + ' entries';
              }
              if (pageNum) {
                pageNum.textContent = 'Page ' + currentPage + ' of ' + totalPages;
              }
              if (prevBtn) prevBtn.disabled = currentPage <= 1;
              if (nextBtn) nextBtn.disabled = currentPage >= totalPages;
            }

            if (prevBtn) {
              prevBtn.addEventListener('click', function() {
                if (currentPage > 1) {
                  currentPage -= 1;
                  renderPage();
                }
              });
            }
            if (nextBtn) {
              nextBtn.addEventListener('click', function() {
                var totalPages = Math.max(1, Math.ceil(rows.length / perPage));
                if (currentPage < totalPages) {
                  currentPage += 1;
                  renderPage();
                }
              });
            }

            headers.forEach(function(th, idx) {
              th.addEventListener('click', function() {
                var current = th.getAttribute('data-sort-dir') || '';
                headers.forEach(function(other) {
                  other.classList.remove('sort-asc', 'sort-desc');
                  other.removeAttribute('data-sort-dir');
                });
                var dir = current === 'asc' ? 'desc' : 'asc';
                th.setAttribute('data-sort-dir', dir);
                th.classList.add(dir === 'asc' ? 'sort-asc' : 'sort-desc');
                rows.sort(function(a, b) {
                  var aText = a.children[idx] ? a.children[idx].innerText : '';
                  var bText = b.children[idx] ? b.children[idx].innerText : '';
                  var av = parseValue(aText);
                  var bv = parseValue(bText);
                  var cmp = 0;
                  if (av.type === 'number' && bv.type === 'number') {
                    cmp = av.value - bv.value;
                  } else {
                    cmp = av.value.localeCompare(bv.value, undefined, {numeric: true, sensitivity: 'base'});
                  }
                  return dir === 'asc' ? cmp : -cmp;
                });
                rows.forEach(function(row) { tbody.appendChild(row); });
                currentPage = 1;
                renderPage();
              });
            });
            renderPage();
          })();
          ",
          table_id,
          pager_id,
          info_id,
          prev_id,
          next_id,
          page_num_id,
          per_page
        )
      )
    )
  )
  htmltools::HTML(htmltools::renderTags(out)$html)
}
