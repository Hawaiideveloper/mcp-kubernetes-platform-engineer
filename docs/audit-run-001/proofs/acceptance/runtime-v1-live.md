# Runtime v1 LIVE — observer loop finding real cluster issues

Generated 2026-06-06T05:16:11Z. main: 6e51789.

## Pod state
```
NAME                              READY   STATUS    RESTARTS   AGE     IP              NODE               NOMINATED NODE   READINESS GATES
auto-remediate-75695d7975-j7tvv   1/1     Running   0          3m27s   10.244.51.193   kubeadm-worker07   <none>           <none>
```

## Observer loop output (3 ticks)
```
2026-06-06 05:14:07,746 INFO auto_remediate.runtime tick=1 findings=21
2026-06-06 05:14:07,746 INFO auto_remediate.runtime finding: albrightlabs-dot-com/Pod/holdings-edge-66c8794cf8-nv5jw sev=medium cat=probe-failure fp=b672e8ccd90c0b76 msg='Probe failure: Readiness probe failed: Get "http://10.244.125.115:80/supply-chain": context deadline exceeded (Client.Timeout exceeded while awaiting headers)'
2026-06-06 05:14:07,746 INFO auto_remediate.runtime finding: brightflow-dashboard/Pod/brightflow-auth-gateway-fc9977fc9-frh47 sev=medium cat=probe-failure fp=5b2464895e5b50fc msg='Probe failure: Readiness probe failed: Get "http://10.244.51.236:8080/ready": context deadline exceeded (Client.Timeout exceeded while awaiting headers)'
2026-06-06 05:14:07,747 INFO auto_remediate.runtime finding: brightflow/Pod/alpha-engine-daily-report-29678400-8jd42 sev=high cat=oom-killed fp=114123b180046f0a msg='init-container/clone OOMKilled (exit_code=137)'
2026-06-06 05:14:07,747 INFO auto_remediate.runtime finding: brightflow/Pod/alpha-engine-market-scanner-29677560-x4sh2 sev=high cat=oom-killed fp=83f36798a4690baa msg='init-container/clone OOMKilled (exit_code=137)'
2026-06-06 05:14:07,747 INFO auto_remediate.runtime finding: brightflow/Pod/data-service-5c6c9c64b5-r94mg sev=critical cat=crash-loop fp=c8ff2c5f716f2b62 msg='init-container/clone crash-looping (restarts=657)'
2026-06-06 05:14:07,747 INFO auto_remediate.runtime finding: brightflow/Pod/execution-service-567b8485cc-r4w9b sev=high cat=crash-loop fp=a411e9334ef7a925 msg='init-container/clone crash-looping (restarts=4)'
2026-06-06 05:14:07,748 INFO auto_remediate.runtime finding: brightflow/Pod/learning-loop-64bfcd598d-gsxg6 sev=critical cat=crash-loop fp=b22efa8708fff79e msg='init-container/clone crash-looping (restarts=707)'
2026-06-06 05:14:07,748 INFO auto_remediate.runtime finding: brightflow/Pod/portfolio-engine-79c564d9df-q2szj sev=critical cat=crash-loop fp=4be70e617c9ea8be msg='init-container/clone crash-looping (restarts=708)'
2026-06-06 05:14:07,748 INFO auto_remediate.runtime finding: brightflow/Pod/strategy-engine-7b9b58997d-8967n sev=medium cat=crash-loop fp=4b74a659db9b3edd msg='init-container/clone crash-looping (restarts=1)'
2026-06-06 05:14:07,748 INFO auto_remediate.runtime finding: calico-apiserver/Pod/calico-apiserver-56f478886c-v5z4r sev=medium cat=probe-failure fp=46f24b4afe7933ac msg='Probe failure: Liveness probe failed: Get "https://10.244.51.105:5443/version": net/http: request canceled (Client.Timeout exceeded while awaiting headers)'
2026-06-06 05:14:07,748 INFO auto_remediate.runtime finding: calico-system/Pod/calico-node-hrdrl sev=medium cat=probe-failure fp=c33cd20102ceafb2 msg='Probe failure: Readiness probe failed: command timed out: "/bin/calico-node -bird-ready -felix-ready" timed out after 10s'
2026-06-06 05:14:07,748 INFO auto_remediate.runtime finding: calico-system/Pod/calico-node-xpdl5 sev=medium cat=probe-failure fp=1b29ba38e1b8932e msg='Probe failure: Readiness probe failed: 2026-06-06 04:40:58.546 [INFO][547529] confd/health.go 180: Number of node(s) with BGP peering established = 8\ncalico/node is not ready: felix is not ready: readiness probe reporting 503\nW0606 04:40:58.537401  547529 feature_gate.go:241] Setting GA feature gate ServiceInternalTrafficPolicy=true. It will be removed in a future release.\n'
2026-06-06 05:14:07,749 INFO auto_remediate.runtime finding: corey-coder/Pod/claude-telephone-proxy-5dddcf654-5h25f sev=high cat=oom-killed fp=0e56c78e5cbbb471 msg='container/proxy OOMKilled (exit_code=137)'
2026-06-06 05:14:07,749 INFO auto_remediate.runtime finding: corey-coder/Pod/corey-fl-agent-688bf4bf5f-6nzw5 sev=high cat=oom-killed fp=cd819a25ef058303 msg='container/agent OOMKilled (exit_code=137)'
2026-06-06 05:14:07,749 INFO auto_remediate.runtime finding: corey-fl-loop/Pod/auto-remediate-75695d7975-j7tvv sev=medium cat=probe-failure fp=08955cc922a65603 msg='Probe failure: Readiness probe failed: '
2026-06-06 05:14:07,749 INFO auto_remediate.runtime finding: google-audit-billing/Pod/gab-google-audit-billing-6ccd58c9c8-sg6t7 sev=critical cat=crash-loop fp=6b41b83de9507ae9 msg='container/dashboard crash-looping (restarts=5)'
2026-06-06 05:14:07,749 INFO auto_remediate.runtime finding: ibkr-live-trader/Pod/composite-gate-775fb47d44-848s5 sev=medium cat=probe-failure fp=cc5e9838b0ed94ec msg='Probe failure: Liveness probe failed: Get "http://10.244.51.197:8090/healthz": context deadline exceeded (Client.Timeout exceeded while awaiting headers)'
2026-06-06 05:14:07,749 INFO auto_remediate.runtime finding: ibkr-live-trader/Pod/daxxon-3-ff6578994-f9mxf sev=high cat=oom-killed fp=8521d92ef02af803 msg='container/daxxon-3-api OOMKilled (exit_code=137)'
2026-06-06 05:14:07,750 INFO auto_remediate.runtime finding: ibkr-live-trader/Pod/fills-writeback-reconciler-29678710-qlbmp sev=high cat=failed-mount fp=b9be5d238ffc96dd msg='FailedMount: MountVolume.SetUp failed for volume "code" : failed to sync configmap cache: timed out waiting for the condition'
2026-06-06 05:14:07,750 INFO auto_remediate.runtime finding: ibkr-live-trader/Pod/ibkr-gateway-restart-alerter-29674410-2zv95 sev=high cat=image-pull fp=e51f0187629e87b0 msg="container/restart-checker cannot pull 'registry.container-registry.svc.cluster.local:5000/library-alpine-k8s:1.31.0': ImagePullBackOff"
2026-06-06 05:14:07,750 INFO auto_remediate.runtime finding: metallb-system/Pod/speaker-ht568 sev=high cat=oom-killed fp=0dad3480e8f28c52 msg='container/speaker OOMKilled (exit_code=137)'
2026-06-06 05:14:49,119 INFO auto_remediate.runtime tick=2 findings=21
2026-06-06 05:15:32,261 INFO auto_remediate.runtime tick=3 findings=21
2026-06-06 05:15:32,261 INFO auto_remediate.runtime finding: ibkr-live-trader/Pod/nick-news-enricher-29678715-n84z8 sev=high cat=failed-mount fp=af92cb968e899a15 msg='FailedMount: MountVolume.SetUp failed for volume "enricher-code" : failed to sync configmap cache: timed out waiting for the condition'
```

## Audit log line count
```
22 /tmp/audit.log
```

## Findings by category (cluster-wide, real)
```
   7 probe-failure
   6 oom-killed
   6 crash-loop
   2 failed-mount
   1 image-pull
```

## Findings by severity
```
  10 high
   8 medium
   4 critical
```

## Trading-namespace handling (per US-006 hardblock)
```
Findings IN trading namespaces (these are observed but never auto-remediated per safety gate):
2026-06-06 05:14:07,749 INFO auto_remediate.runtime finding: ibkr-live-trader/Pod/composite-gate-775fb47d44-848s5 sev=medium cat=probe-failure fp=cc5e9838b0ed94ec msg='Probe failure: Liveness probe failed: Get "http://10.244.51.197:8090/healthz": context deadline exceeded (Client.Timeout exceeded while awaiting headers)'
2026-06-06 05:14:07,749 INFO auto_remediate.runtime finding: ibkr-live-trader/Pod/daxxon-3-ff6578994-f9mxf sev=high cat=oom-killed fp=8521d92ef02af803 msg='container/daxxon-3-api OOMKilled (exit_code=137)'
2026-06-06 05:14:07,750 INFO auto_remediate.runtime finding: ibkr-live-trader/Pod/fills-writeback-reconciler-29678710-qlbmp sev=high cat=failed-mount fp=b9be5d238ffc96dd msg='FailedMount: MountVolume.SetUp failed for volume "code" : failed to sync configmap cache: timed out waiting for the condition'
2026-06-06 05:14:07,750 INFO auto_remediate.runtime finding: ibkr-live-trader/Pod/ibkr-gateway-restart-alerter-29674410-2zv95 sev=high cat=image-pull fp=e51f0187629e87b0 msg="container/restart-checker cannot pull 'registry.container-registry.svc.cluster.local:5000/library-alpine-k8s:1.31.0': ImagePullBackOff"
2026-06-06 05:15:32,261 INFO auto_remediate.runtime finding: ibkr-live-trader/Pod/nick-news-enricher-29678715-n84z8 sev=high cat=failed-mount fp=af92cb968e899a15 msg='FailedMount: MountVolume.SetUp failed for volume "enricher-code" : failed to sync configmap cache: timed out waiting for the condition'
```
