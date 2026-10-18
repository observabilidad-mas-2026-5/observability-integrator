$ErrorActionPreference = 'Continue'
$repo = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$evidence = Join-Path $repo 'docs/evidence'
foreach ($cloud in @('aws', 'gcp')) {
    $infraPath = Join-Path $repo "infra/$cloud"
    $volume = "otel-credit-terraform-$cloud"
    $initArgs = @('run', '--rm', '--mount', "type=bind,source=$infraPath,target=/source,readonly", '--mount', "type=volume,source=$volume,target=/work", '-w', '/work', '--entrypoint', '/bin/sh', 'hashicorp/terraform:1.13.3', '-c', 'cp /source/main.tf.json /work/main.tf.json && if [ -f /source/.terraform.lock.hcl ]; then cp /source/.terraform.lock.hcl /work/.terraform.lock.hcl; fi && terraform init -backend=false -input=false -no-color')
    $init = & docker @initArgs 2>&1
    $exitCode = $LASTEXITCODE
    $init | Set-Content -Encoding UTF8 (Join-Path $evidence "terraform-$cloud-init.txt")
    if ($exitCode -ne 0) { $init; throw "Terraform init $cloud failed" }
    $validation = & docker run --rm --mount "type=volume,source=$volume,target=/work" -w /work -e TF_PLUGIN_TIMEOUT=300s hashicorp/terraform:1.13.3 validate -json
    $exitCode = $LASTEXITCODE
    $validation | Set-Content -Encoding UTF8 (Join-Path $evidence "terraform-$cloud-validate.json")
    if ($exitCode -ne 0) { $validation; throw "Terraform validate $cloud failed" }
    $lock = & docker run --rm --mount "type=volume,source=$volume,target=/work" --entrypoint /bin/cat hashicorp/terraform:1.13.3 /work/.terraform.lock.hcl
    $lock | Set-Content -Encoding UTF8 (Join-Path $infraPath '.terraform.lock.hcl')
    Write-Output "Terraform $cloud validado"
}
