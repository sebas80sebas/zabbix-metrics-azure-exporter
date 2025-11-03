# Pasos de despliegue
1. Inicializar Terraform
```bash
cd terraform/
terraform init
```
2. Crear archivo terraform.tfvars
```bash
cp terraform.tfvars.example terraform.tfvars
# Editar con tus valores reales
nano terraform.tfvars
```
3. Validar configuración
```bash
terraform validate
terraform plan
```
4. Desplegar
```bash
terraform apply
```
5. Ver outputs
```bash
terraform output
terraform output -json
```
