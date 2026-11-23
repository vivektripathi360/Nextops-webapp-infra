resource_group_name = {
  rg = {
    rg_name  = "nextops_rg"
    location = "Australia Central"
  }
}

service_plan = {
  plan = {
    plan_name = "nextops-plan"
    os_type   = "Linux"
    sku_name  = "B1"
  }
}

web_app = {
  frontend = {
    web_app_name = "nextops-frontend-vk123"
  }

  backend = {
    web_app_name = "nextops-backend-vk123"
  }
}

postgresql = {
  pg = {
    server_name       = "nextops-pg-vk123"
    admin_username    = "nextopsadmin"
    postgres_password = "vivek!1234"
    database_name     = "nextopsdb"
    sku_name          = "B_Standard_B1ms"
  }
}


