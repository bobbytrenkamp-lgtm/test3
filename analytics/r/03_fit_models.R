source("analytics/r/02_prepare_features.R")
model <- lm(rent_growth_12m ~ period_index + vacancy_rate, data=features)
coefs <- data.frame(term=names(coef(model)), estimate=unname(coef(model)), std_error=coef(summary(model))[,2], warning=warning_label)
