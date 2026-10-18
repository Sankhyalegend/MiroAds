# End-to-end smoke test against a running API (default http://localhost:8000).
param([int]$Crowd = 150, [int]$Rounds = 3, [string]$Api = "http://localhost:8000")

$h = Invoke-RestMethod "$Api/health"
"health: provider=$($h.provider) crowd=$($h.crowdModel) analyst=$($h.analystModel) library=$($h.library)"

$stim = @{
  type = "creative"; title = "Nightshift launch poster"
  brief = 'Poster shows a dim home office at night, a desk lamp glowing amber over a closed laptop. Tagline: "Your light knows when to stop." Small text: Nightshift smart desk lamp, $149, shifts colour temperature with your calendar. Early-bird $30 off for first 500.'
  targetAudience = "Remote software developers 25-40, students, productivity enthusiasts; plus a general-public control sample"
} | ConvertTo-Json
$s = Invoke-RestMethod -Method Post -Uri "$Api/stimuli" -ContentType "application/json" -Body $stim
"stimulus: $($s.id)"

$runBody = @{ stimulus_id = $s.id; crowdSize = $Crowd; rounds = $Rounds; seed = 7 } | ConvertTo-Json
$r = Invoke-RestMethod -Method Post -Uri "$Api/runs" -ContentType "application/json" -Body $runBody
"run: $($r.id) personas=$($r.personas.Count) status=$($r.status)"

$t0 = Get-Date
do {
  Start-Sleep -Seconds 3
  $st = Invoke-RestMethod "$Api/runs/$($r.id)"
  $evs = Invoke-RestMethod "$Api/runs/$($r.id)/events?from_seq=0"
  $kinds = $evs | Group-Object kind | ForEach-Object { "$($_.Name)=$($_.Count)" }
  "$(((Get-Date) - $t0).TotalSeconds.ToString('0'))s status=$($st.status) stage=$($st.stage) cost=`$$($st.costUsd) events: $($kinds -join ' ')"
} while ($st.status -in @('queued', 'running') -and ((Get-Date) - $t0).TotalMinutes -lt 15)

if ($st.status -eq 'failed') { "ERROR: $($st.error)"; exit 1 }
$sc = Invoke-RestMethod "$Api/runs/$($r.id)/scorecard"
""
"=== SCORECARD ==="
"overall=$($sc.overall)  verdict: $($sc.verdict)"
"intent: buy $($sc.intentSplit.buy)% maybe $($sc.intentSplit.maybe)% no $($sc.intentSplit.no)%  polarization=$($sc.polarization) shift=$($sc.shift)"
"confidence: $($sc.confidence.label) ($($sc.confidence.agreement)% agreement, n=$($sc.confidence.sample)) $($sc.confidence.note)"
"summary: $($sc.summary)"
"dimensions: " + (($sc.dimensions | ForEach-Object { "$($_.name)=$($_.score)" }) -join ', ')
"top objections:"; $sc.objections | Select-Object -First 4 | ForEach-Object { "  $($_.count)x [$($_.influence)] $($_.text)" }
"missing KPIs:"; $sc.missingKpis | Select-Object -First 4 | ForEach-Object { "  - $($_.kpi) ($($_.by)): $($_.target)" }
"variants:"; $sc.variants | ForEach-Object { "  $($_.predictedDelta): $($_.label)" }
"diversity: $($sc.research.diversity | ConvertTo-Json -Compress)"
"cost: `$$($sc.research.costUsd) provider=$($sc.research.provider) models=$($sc.research.models | ConvertTo-Json -Compress)"
$a = Invoke-RestMethod "$Api/runs/$($r.id)/agents/0"
"agent 0: $($a.name), $($a.profession), $($a.region), mood=$($a.mood) verdict=$($a.verdict.score) actions=$($a.actions.Count)"
"  reasoning: $($a.verdict.reasoning)"
