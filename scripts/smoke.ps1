$ErrorActionPreference = 'Stop'
$live = Invoke-RestMethod 'http://127.0.0.1:8000/health/live'
if ($live.status -ne 'ok') { throw 'Liveness failed' }
$ready = Invoke-RestMethod 'http://127.0.0.1:8000/health/ready'
if ($ready.status -ne 'ready' -or $ready.db -ne 'ok') { throw 'Database not ready' }
$proxied = Invoke-RestMethod 'http://127.0.0.1:5173/health/ready'
if ($proxied.db -ne 'ok') { throw 'Frontend API proxy failed' }
$system = Invoke-RestMethod 'http://127.0.0.1:5173/api/v1/system'
if ($system.mode -ne 'local_demo') { throw 'Wrong application mode' }
$companies = Invoke-RestMethod 'http://127.0.0.1:5173/api/v1/companies?limit=100'
$checkedResults = 0
foreach ($company in $companies) {
    $employees = Invoke-RestMethod "http://127.0.0.1:5173/api/v1/companies/$($company.id)/employees?limit=100"
    foreach ($employee in $employees) {
        if ($employee.company_id -ne $company.id) { throw 'Employee company mismatch' }
    }
    $calls = Invoke-RestMethod "http://127.0.0.1:5173/api/v1/companies/$($company.id)/calls?limit=100"
    foreach ($call in $calls) {
        if ($call.company_id -ne $company.id) { throw 'Call company mismatch' }
        if ($call.status -eq 'completed') {
            $base = "http://127.0.0.1:5173/api/v1/companies/$($company.id)/calls/$($call.id)"
            $transcript = Invoke-RestMethod "$base/transcript"
            $analysis = Invoke-RestMethod "$base/analysis"
            if ($analysis.run_id -ne $call.run_id -or $transcript.run_id -ne $call.run_id) { throw 'Result run mismatch' }
            if ($call.is_mock -and (-not $analysis.is_mock -or -not $transcript.is_mock)) { throw 'Mock labels missing' }
            $segmentIds = @($transcript.segments | ForEach-Object { $_.segment_id })
            foreach ($criterion in $analysis.criterion_results) {
                foreach ($segmentId in $criterion.evidence_segment_ids) {
                    if ($segmentIds -notcontains $segmentId) { throw 'Invalid criterion evidence' }
                }
            }
            foreach ($objection in $analysis.objections) {
                foreach ($segmentId in $objection.evidence_segment_ids) {
                    if ($segmentIds -notcontains $segmentId) { throw 'Invalid objection evidence' }
                }
            }
            $checkedResults++
        }
    }
    $firstCall = $calls | Select-Object -First 1
    if ($firstCall) {
        $audioRequest = [System.Net.WebRequest]::Create("http://127.0.0.1:5173/api/v1/companies/$($company.id)/calls/$($firstCall.id)/audio")
        $audioRequest.AddRange(0, 9)
        $audio = $audioRequest.GetResponse()
        try {
            if ([int]$audio.StatusCode -ne 206) { throw 'Audio Range request failed' }
        } finally {
            $audio.Close()
        }
    }
}
$page = Invoke-WebRequest 'http://127.0.0.1:5173' -UseBasicParsing
if ($page.Content -notmatch 'id="root"') { throw 'Frontend page missing' }
Write-Output "Smoke OK: API, PostgreSQL, frontend, companies, employees, calls, audio. Validated results: $checkedResults."
