# Deployment Guide: Zabbix Metrics Azure Exporter

This guide provides three alternative methods to deploy the infrastructure required for the Zabbix Metrics Azure Exporter.

## 1. Automated Deployment with Terraform

This is the recommended method for consistency and speed.

### Version Information
*   **Terraform Required Version:** `>= 1.0`
*   **AzureRM Provider:** `~> 4.0`
*   **AzAPI Provider:** `~> 2.0`

### Steps
1.  Navigate to the `terraform/` directory.
2.  Copy `terraform.tfvars.example` to `terraform.tfvars` and fill in your Zabbix and Teams credentials.
3.  Execute the following commands:
    ```bash
    terraform init
    terraform plan
    terraform apply
    ```

---

## 2. Manual Deployment via Azure CLI (CLI/ARM Alternative)

If you prefer using the command line without Terraform, follow these steps using the Azure CLI.

### Resource Group & Networking
```bash
# 1. Create Resource Group
az group create --name "rg_zabbix_exporter" --location "westeurope"

# 2. Create VNet
az network vnet create \
  --name vnet-zabbix-exporter \
  --resource-group rg_zabbix_exporter \
  --location westeurope \
  --address-prefix 10.0.0.0/16

# 3. Create 'default' subnet
az network vnet subnet create \
  --name default \
  --resource-group rg_zabbix_exporter \
  --vnet-name vnet-zabbix-exporter \
  --address-prefix 10.0.0.0/24

# 4. Create 'functions' subnet with delegation
az network vnet subnet create \
  --name functions \
  --resource-group rg_zabbix_exporter \
  --vnet-name vnet-zabbix-exporter \
  --address-prefix 10.0.1.0/24 \
  --service-endpoints Microsoft.Storage Microsoft.KeyVault \
  --delegations Microsoft.App/environments
```

### Storage Account
```bash
# 5. Create Storage Account
az storage account create \
  --name stzabbixexporter \
  --resource-group rg_zabbix_exporter \
  --location westeurope \
  --sku Standard_LRS \
  --kind StorageV2 \
  --https-only true \
  --min-tls-version TLS1_2

# 6. Enable Retention Policies
az storage account blob-service-properties update \
  --account-name stzabbixexporter \
  --resource-group rg_zabbix_exporter \
  --enable-delete-retention true --delete-retention-days 7 \
  --enable-container-delete-retention true --container-delete-retention-days 7

# 7. Create Containers
ACCOUNT_KEY=$(az storage account keys list --account-name stzabbixexporter --resource-group rg_zabbix_exporter --query '[0].value' -o tsv)

az storage container create --name azure-webjobs-hosts --account-name stzabbixexporter --account-key $ACCOUNT_KEY
az storage container create --name azure-webjobs-secrets --account-name stzabbixexporter --account-key $ACCOUNT_KEY
az storage container create --name metrics --account-name stzabbixexporter --account-key $ACCOUNT_KEY
```

### Identity & Key Vault
```bash
# 8. Create Managed Identity
az identity create --name "func-zabbix-exporter-uami" --resource-group rg_zabbix_exporter

# 9. Create Key Vault
az keyvault create \
  --name "kv-zabbix-exporter" \
  --resource-group rg_zabbix_exporter \
  --location westeurope \
  --sku standard

# 10. Set Access Policies
USER_ID=$(az ad signed-in-user show --query id -o tsv)
IDENTITY_ID=$(az identity show --name "func-zabbix-exporter-uami" --resource-group rg_zabbix_exporter --query principalId -o tsv)

az keyvault set-policy --name "kv-zabbix-exporter" --object-id $USER_ID --secret-permissions get list set delete
az keyvault set-policy --name "kv-zabbix-exporter" --object-id $IDENTITY_ID --secret-permissions get list
```

### Function App (Flex Consumption)
```bash
# 11. Create Application Insights
az monitor app-insights component create --app "func-zabbix-exporter" --location "westeurope" --resource-group rg_zabbix_exporter --application-type web

# 12. Create Function App
az functionapp create \
  --name "func-zabbix-exporter" \
  --resource-group rg_zabbix_exporter \
  --storage-account stzabbixexporter \
  --assign-identity "func-zabbix-exporter-uami" \
  --os-type Linux \
  --runtime python \
  --runtime-version 3.12 \
  --functions-version 4 \
  --flexconsumption-location "westeurope"
```

---

## 3. Manual Deployment via Azure Portal

For users who prefer a graphical interface.

### Step 1: Resource Group
*   Go to **Resource Groups** -> **Create**.
*   Name: `rg_zabbix_exporter`.
*   Region: `West Europe`.

### Step 2: Virtual Network
*   Create a **Virtual Network** named `vnet-zabbix-exporter`.
*   Address space: `10.0.0.0/16`.
*   Add a subnet named `default` (`10.0.0.0/24`).
*   Add a subnet named `functions` (`10.0.1.0/24`).
    *   Under **Subnet delegation**, select `Microsoft.App/environments`.
    *   Enable **Service Endpoints** for `Microsoft.Storage` and `Microsoft.KeyVault`.

### Step 3: Storage Account
*   Create a **Storage Account** named `stzabbixexporter`.
*   Performance: `Standard`. Redundancy: `LRS`.
*   Under **Data protection**, enable point-in-time restore and soft delete for blobs/containers (7 days).
*   In **Networking**, allow access from the `functions` subnet of your VNet.
*   Create three containers: `azure-webjobs-hosts`, `azure-webjobs-secrets`, and `metrics`.

### Step 4: Managed Identity & Permissions
*   Create a **User Assigned Managed Identity** named `func-zabbix-exporter-uami`.
*   Go to your **Storage Account** -> **Access Control (IAM)** -> **Add role assignment**.
*   Role: `Storage Blob Data Owner`.
*   Assign access to: `Managed identity` -> Select `func-zabbix-exporter-uami`.

### Step 5: Key Vault
*   Create a **Key Vault** named `kv-zabbix-exporter`.
*   In **Access configuration**, ensure you (the current user) have `Secret Management` permissions.
*   Add an access policy for the `func-zabbix-exporter-uami` with `Get` and `List` secret permissions.
*   Add the following **Secrets**: `ZABBIX-URL`, `ZABBIX-USER`, `ZABBIX-PASSWORD`, `TEAMS-WEBHOOK-URL`.

### Step 6: Function App
*   Create a **Function App**.
*   Runtime stack: `Python 3.12`.
*   Operating System: `Linux`.
*   Plan type: `Flex Consumption`.
*   **Networking:** Enable VNet integration and select the `functions` subnet.
*   **Identity:** Under Settings -> Identity, add the `func-zabbix-exporter-uami`.
*   **Configuration:** Add the Environment Variables (App Settings) pointing to Key Vault or direct values as needed.

---

## 4. Power Automate Workflow

To receive the notifications in Teams:
1.  In Teams, go to **Workflows** -> **Create from blank**.
2.  Trigger: **"When a Teams webhook request is received"**.
3.  Copy the generated URL and save it as `TEAMS_WEBHOOK_URL` in the Azure Function settings.
4.  Action: **"Post a message in a chat or channel"**.
5.  Message content: Use the dynamic expression `@{triggerBody()?['mensaje_completo']}`.

