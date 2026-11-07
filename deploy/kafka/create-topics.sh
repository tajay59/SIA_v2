#!/usr/bin/env bash
# Create every topic from TAD §5 (idempotent). Prod: REPLICATION=3, min.insync.replicas=2.
set -euo pipefail
B=${BOOTSTRAP:-kafka:9092}; R=${REPLICATION:-3}
KT=/opt/kafka/bin/kafka-topics.sh
until $KT --bootstrap-server "$B" --list >/dev/null 2>&1; do echo "waiting for kafka"; sleep 2; done
mk() { # name partitions retention-ms|compact
  local name=$1 parts=$2 ret=$3 cfg
  if [ "$ret" = compact ]; then cfg="--config cleanup.policy=compact"; else cfg="--config retention.ms=$ret"; fi
  $KT --bootstrap-server "$B" --create --if-not-exists --topic "$name" --partitions "$parts" --replication-factor "$R" $cfg
}
DAY=86400000
mk identity.user.events 6 compact
mk catalog.product.events 12 compact
mk inventory.stock.events 12 $((7*DAY))
mk order.events 12 $((7*DAY))
mk document.events 6 $((7*DAY))
mk media.jobs 4 $((3*DAY))
mk media.results 4 $((3*DAY))
mk audit.events 6 $((30*DAY))
for t in identity.user.events catalog.product.events inventory.stock.events order.events document.events media.jobs media.results audit.events; do
  p=$($KT --bootstrap-server "$B" --describe --topic "$t" | grep -o 'PartitionCount: *[0-9]*' | grep -o '[0-9]*$')
  mk "$t.retry" "$p" $((14*DAY)); mk "$t.dlq" "$p" $((14*DAY))
done
echo "topics ready"
