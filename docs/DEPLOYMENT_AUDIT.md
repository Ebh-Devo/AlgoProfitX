I’ll trace the deployment surfaces in the checked-out repository first, then inspect the separate connectivity repository through its public GitHub contents and compare references across both. I’ll keep all changes limited to a new audit report, with no configuration, secrets, application code, or deployment actions touched.

Read memory

Ran terminal command: Get-ChildItem -Force; git remote -v; git status --short; git branch -a

Read 

Search complete: Audit primary deployment paths

Searched codebase for "AlgoProfitX CI workflows deployment scripts Dockerfiles Catalyst CLI configuration", no results

Searched codebase for "AppSail names IDs environments secrets smoke tests health checks rollback", no results

Searched codebase for "artifact naming Git SHA traceability documentation", no results

Searched for files matching `**/*ci*.{yml,yaml,js,py,go,java}`, 6 matches

Searched for files matching `**/*deploy*.{yml,yaml,js,py,go,java,sh}`, 5 matches

Searched for files matching `**/*docker*.{yml,yaml,sh,js,py,go}`, 2 matches

Searched for files matching `**/catalyst*.{yml,yaml,js,py,go,java}`, no matches

Searched for files matching `**/appsail*.{yml,yaml,js,py,go,java}`, no matches

Searched for files matching `**/*secret*.{yml,yaml,js,py,go,java}`, no matches

Searched for files matching `**/*health*.{yml,yaml,js,py,go,java,sh}`, 2 matches

Searched for files matching `**/*.md`, 18 matches

Searched for files matching `**/docs/**`, 8 matches

Searched for files matching `**/release/**`, no matches

Searched for files matching `**/appsail/**`, no matches

Read 

Read 

Read 

Read 

Read 

Read 

Read 

Read 

Read 

Read 

Read 

Read 

Read 

Read 

Read , lines 1 to 260

Read 

Read 

Read 

Read 

Read 

The primary repository already contains Catalyst deployment workflows, including a reviewed immutable release path for Development, while its runtime documentation still says production deployment is not implemented. I’m now checking every workflow and deployment-related reference, and I’ll clone the separate repository into a temporary directory solely for read-only comparison.

Ran terminal command: Get-ChildItem .github\workflows -File | Select-Object -ExpandProperty FullName; Get-ChildItem backend,frontend,deploy,scripts,docs -Recurse -File | Where-Object { $_.Name -match 'Docker|docker|deploy|catalyst|release|health|version|env|runtime|production|staging' } | Select-Object -ExpandProperty FullName
Completed with input: Get-ChildItem .github\workflows -File | Select-Object -ExpandProperty FullName; Get-ChildItem backend,frontend,deploy,scripts,docs -Recurse -File | Where-Object { $_.Name -match 'Docker|docker|deploy|catalyst|release|health|version|env|runtime|production|staging' } | Select-Object -ExpandProperty FullName

Ran terminal command: $temp = Join-Path $env:TEMP 'algoprofitx-connectivity-audit'; if (Test-Path $temp) { Remove-Item -Recurse -Force $temp }; git clone --depth 1 https://github.com/Ebh-Devo/algoprofitx-catalyst-connectivity-poc.git $temp; Get-ChildItem $temp -Force; git -C $temp log -1 --format='%H%n%ad%n%s' --date=iso

Ran terminal command: Get-ChildItem backend -Recurse -File | Select-String -Pattern 'APP_SOURCE|VCS_REF|SOURCE_URL|version|release|commit|sha|health/live|health/ready' | Select-Object Path,LineNumber,Line
Completed with input: Get-ChildItem backend -Recurse -File | Select-String -Pattern 'APP_SOURCE|VCS_REF|SOURCE_URL|version|release|commit|sha|health/live|health/ready' | Select-Object Path,LineNumber,Line

Searching for regex `connectivity-poc|algoprofitx-catalyst-connectivity-poc|Catalyst|catalyst|36851000000392052|algoprofitx-web|algoprofitx-api|deployment|rollback|smoke|health|VCS_REF|APP_SOURCE_SHA|image`

The separate repository is very small: a single Python service, one Dockerfile, requirements, and one GitHub workflow directory. The first broad text search timed out on generated/working-tree content, so I’m narrowing the audit to tracked files and exact deployment tokens; this will also distinguish real dependencies from duplicated or untracked material in the primary worktree.

Ran terminal command: git ls-files .github backend frontend deploy scripts docs Dockerfile* docker-compose.yml README.md | ForEach-Object { $_ }; git ls-files .github/workflows | ForEach-Object { Write-Output "--- $_"; Get-Content $_ }

Ran terminal command: $temp = Join-Path $env:TEMP 'algoprofitx-connectivity-audit'; git -C $temp ls-files | ForEach-Object { Write-Output "--- $_"; Get-Content (Join-Path $temp $_) }

Ran terminal command: Get-ChildItem backend -Recurse -File | Select-String -Pattern 'APP_SOURCE|VCS_REF|SOURCE_URL|health/live|health/ready|version|commit|sha' | Select-Object Path,LineNumber,Line; Get-ChildItem frontend -Recurse -File | Select-String -Pattern 'version|commit|sha|health|api.algoprofitx|staging' | Select-Object Path,LineNumber,Line

Ran terminal command: git ls-files | Select-String -Pattern '(^|/)(Dockerfile[^/]*|.*deploy.*|.*catalyst.*|.*release.*|.*production.*|.*staging.*|.*health.*|.*env.*|.*version.*)$' | ForEach-Object { $_ }; Get-ChildItem .github\workflows -File | Select-Object -ExpandProperty Name

Read , lines 1 to 260

Read , lines 1 to 240

Read 

Read 

Read 

Read 

Read 

The POC’s actual role is now clear: it builds and manually deploys a standalone `connectivity-poc` AppSail in Catalyst Development, with a DB/TLS connectivity probe and no production deployment logic. The primary repo’s direct Catalyst workflows target `algoprofitx-api` and `algoprofitx-web`; I’m tightening the evidence around the exact build/verify gates, AppSail target names, and whether any primary workflow calls the POC repository.

Ran terminal command: $patterns = 'connectivity-poc','algoprofitx-catalyst-connectivity-poc','Ebh-Digtal','Ebh-Devo','Ebhadmin','36851000000392052','algoprofitx-web','algoprofitx-api','catalyst deploy','zcatalyst-cli','CATALYST_TOKEN','deployment ID','run-id'; git grep -n -I -E ($patterns -join '|') -- . ':!frontend/node_modules' ':!.release' 2>$null; Write-Output '--- POC references'; $temp = Join-Path $env:TEMP 'algoprofitx-connectivity-audit'; git -C $temp grep -n -I -E ($patterns -join '|') -- . 2>$null

Read 

Read 

Read 

Read 

Read 

Ran terminal command: $files = @('.github/workflows/build-catalyst.yml','.github/workflows/deploy-catalyst-development.yml','.github/workflows/deploy-catalyst-api.yml','.github/workflows/verify-catalyst-api.yml','scripts/verify-api-runtime.py','backend/Dockerfile','frontend/Dockerfile','docs/production-runtime.md','docs/deployment-digitalocean-staging.md'); foreach ($file in $files) { Write-Output "--- $file"; $i=0; Get-Content $file | ForEach-Object { $i++; if ($_ -match 'name:|on:|branches:|workflow_dispatch|run:|uses:|CATALYST|catalyst|repository:|run-id:|artifact|sha|VCS_REF|SOURCE_URL|APP_SOURCE|DEPLOYMENT_REPO|HEALTHCHECK|health|No production|DigitalOcean|manual|rollback|deployment') { '{0}:{1}' -f $i,$_ } } }

Read 

Read 

Read 

Read 

I found the key cross-repository fact: the primary API runtime metadata explicitly records the POC repository and a fixed POC commit as `DEPLOYMENT_REPO`/`DEPLOYMENT_SHA`, but the actual primary Catalyst deployment commands build and deploy AlgoProfitX archives from the primary repository. That makes the POC a traceability/documentation dependency and a separate Development connectivity deployment, not the current API/web production release path. I’m writing the audit with that distinction, plus the repository-name mismatches and missing production automation called out as blockers.

Created 

The audit report is now written as a new Markdown document only. I’m doing a focused integrity check on the report and worktree status, then I’ll summarize the findings and explicitly separate repository evidence from live production facts that were not queried.

Ran terminal command: $report = 'DEPLOYMENT_ARCHITECTURE_AUDIT.md'; if (-not (Test-Path $report)) { throw 'Audit report was not created' }; $required = @('## A. Current Architecture','## B. Dependency Matrix','## C. Current Development Deployment','## D. Current Production Deployment','## E. Git SHA Traceability','## F. Recommended Target Architecture','## G. Migration Plan','## H. POC Retirement Criteria','AUDIT COMPLETE'); $content = Get-Content $report -Raw; $missing = $required | Where-Object { $content -notmatch [regex]::Escape($_) }; if ($missing) { throw ('Missing report sections: ' + ($missing -join ', ')) }; $lines = Get-Content $report; if (($lines | Where-Object { $_ -match '[^