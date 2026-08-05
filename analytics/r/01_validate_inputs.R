source("analytics/r/00_helpers.R")
panel <- read.csv("analytics/fixtures/fictional_market_panel.csv", stringsAsFactors=FALSE)
assert_columns(panel, c("period","market_id","property_type","rent_growth_12m","vacancy_rate"))
if (any(!is.finite(panel$rent_growth_12m)) || any(abs(panel$rent_growth_12m) > 1)) stop("Invalid growth rate")
