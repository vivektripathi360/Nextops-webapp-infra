resource "azurerm_resource_group" "nextops" {
  for_each = var.resource_group_name

  name     = each.value.rg_name
  location = each.value.location
}

resource "azurerm_service_plan" "nextops1" {
  for_each = var.service_plan

  name                = each.value.plan_name
  resource_group_name = azurerm_resource_group.nextops["rg"].name
  location            = azurerm_resource_group.nextops["rg"].location

  os_type  = each.value.os_type
  sku_name = each.value.sku_name
}

resource "azurerm_linux_web_app" "nextops2" {
  for_each = var.web_app

  name                = each.value.web_app_name
  resource_group_name = azurerm_resource_group.nextops["rg"].name
  location            = azurerm_resource_group.nextops["rg"].location

  service_plan_id = azurerm_service_plan.nextops1["plan"].id

  site_config {
    always_on = false
  }
}

resource "azurerm_postgresql_flexible_server" "nextops3" {
  for_each = var.postgresql

  name                = each.value.server_name
  resource_group_name = azurerm_resource_group.nextops["rg"].name
  location            = azurerm_resource_group.nextops["rg"].location


  version                = "16"
  administrator_login    = each.value.admin_username
  administrator_password = each.value.postgres_password

  sku_name   = each.value.sku_name
  storage_mb = 32768

  backup_retention_days = 7

  public_network_access_enabled = true
}

resource "azurerm_postgresql_flexible_server_database" "nextops4" {
  for_each = var.postgresql

  name      = each.value.database_name
  server_id = azurerm_postgresql_flexible_server.nextops3[each.key].id

  charset   = "UTF8"
  collation = "en_US.utf8"
}
