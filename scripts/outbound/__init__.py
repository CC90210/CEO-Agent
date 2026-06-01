"""scripts/outbound/ — caller-facing outbound workflows.

These tools COMPOSE send_gateway.send() into higher-level operations
(multi-recipient threaded sends, etc.) without bypassing the chokepoint
that enforces CASL, cooldowns, and the per-user OAuth identity policy.

Add new outbound workflows here, not in send_gateway itself —
send_gateway is the transport, this directory is the policy.
"""
