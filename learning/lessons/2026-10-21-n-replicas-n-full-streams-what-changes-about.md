Phase 0 left you able to spot the failure a health check cannot see, which is a watcher running on stale data. You scaled the watcher in your own stack to five replicas because one was busy. Each replica now costs more than one replica did before, because all five receive every change the cluster makes and each one parses and throws away most of it. Phase 0 drew the API server feeding each control loop, so adding replicas looked like work that divides between them.

What is still open is what decides which changes reach which replica. One answer is a filter that runs in the API server before it sends anything, which would divide the cost. Another is a shared record that names the slice of the world each replica owns. This lesson asks when those two things exist, and what your code must do when nothing enforces the split.

- Filtering a stream after delivery saves nothing, so each replica pays for the full stream; only a filter at the source divides the cost, and it can silently not run. Predict what scaling a watcher costs and decide when to trust a server-side filter.

## Why does adding replicas make each one more expensive?

Adding replicas does not divide the read cost, because every replica still receives every change.

A watcher lists and watches a whole collection. It caches service endpoints or config by reading the world from the API server. Suppose it runs as five replicas. Each replica now pays the full cost of reading the world, not a fifth of it, so you want that number before you add a sixth.

The watcher is a control loop, the pattern behind level-triggered reconciliation. It reads the world, compares it with the desired state (the record of what should be true), then acts on the difference. It reads from the API server, the process that reads from etcd. The API server sends changes to each replica on a watch stream, the open connection that carries every change in one collection.

  collection: 100,000 pods

-

  API server

-

-

-

-

-
  watch stream

  replica 1

  replica 2

  replica 3

  replica 4

  replica 5

One collection behind one API server. Each replica holds its own watch stream.

Predict: does each replica get cheaper as you add them?
A controller reads the whole world on a cluster where objects keep changing. You run 1 replica, then 5. Does each replica's cost of reading the world fall, stay flat, or rise?

Stay flat. Each replica still receives the full stream of changes, so its cost of reading the world does not move. The fleet now pays five full streams instead of one. The tempting answer is fall, and it is reasonable: one request goes to one replica, so the work looks divisible between them.

Every change takes the same path before your code can look at it, and the cost of reading the world sits in that path.

- One object in the collection changes. The API server writes the new version and appends one change to the watch stream of every replica.

- Nothing at this step knows who owns the object. Each replica subscribed to the whole collection, so the API server sends every change to every replica.

- Each replica turns the bytes back into an object before it can inspect it. That work is the decode cost, the CPU and memory one change costs to parse.

- Your own rule then drops the change when another replica owns the object. Splitting work this way is client-side sharding, where each replica filters for itself after delivery.

- The fleet pays N times the full stream to do one stream of work. The Kubernetes blog states that cost as N replicas times the full stream of changes.

  What your fleet decodes per minute

  Replicas

  Each replica decodes  objects per minute

  The fleet decodes  objects per minute

  Each replica keeps  of them

The rate above is 40,000 object changes per minute. It is assumed for this lesson and not measured, and it is what each watch stream is charged for. The 100,000 pods set the size of the cache, not the rate.

At five replicas, the fleet decodes the whole stream five times and keeps one share of it. Per replica, the CPU, memory and network cost stays at full stream while each keeps only its own share. The budget now scales with the churn of the whole cluster, and one more replica adds one more full stream.

Two quantities matter: the changes a replica receives, and the changes it owns. The share of decode cost spent on thrown-away changes is (received − owned) divided by received.

N replicas cost N full streams, because each one decodes every change and keeps a share.

You expect one request to land on one replica, so the work looks divisible. That is not what happens, because the API server sends every change to every watcher and the fleet pays five full streams.

Move the slider from 1 to 5 replicas and watch two numbers. The fleet number multiplies and the per-replica number stays flat.

The drop step saves nothing, so the only place left to filter is before the stream reaches each replica. The next section moves that filter into the API server.

## What did v1.36 move into the API server?

The section above shows that filtering after delivery multiplies cost per replica, but not where the filter can move.

Claim a hash range and the API server sends you only your share of changes.

Your endpoint cache at five replicas lists and watches the whole collection. It deserializes every object and discards the ones outside its shard because client-side sharding filters after the decode. The API server can drop the objects outside a shard's range before they travel over the wire.

40,000 object changes per minute is assumed for this lesson and not measured.

A list or watch request can now carry a shardSelector, a field that names one object field. It also names a span of numbers. The API server turns that field into a number with a hash. The hash is a formula that maps any input to a fixed range of numbers. It sends only the objects whose number falls in the hash range, the span of values your request claims. It sends them in the list response and in the watch stream. Ownership moves from your decoder to the sender, so the stream itself shrinks.

  object change

-

  API server
  hash the field, compare the range

-
  this object's hash

  the 64-bit hash space

  0x0000…0000
  0x3333…3333
  0x6666…6666
  0x9999…9999
  0xCCCC…CCCC
  0xFFFF…FFFF

-

-

-

-

-

  no event
  this event

  replica 1
  8,000 per minute

  replica 2
  8,000 per minute

  replica 3
  8,000 per minute

  replica 4
  8,000 per minute

  replica 5
  8,000 per minute

One change and five claimed hash ranges across the 64-bit space. The server sends the object only to the replica whose range holds its hash, so each replica decodes only the objects inside its own range. The five ranges split evenly here and are drawn to show the shape.

Server-side sharding is alpha since v1.36, behind the ShardedListAndWatch feature gate on kube-apiserver.

- Your replica sends a list and watch request whose shardSelector has this shape.
shardRange(object.metadata.uid, 0x0000000000000000, 0x8000000000000000)

The first argument names the field, and the last two give the bounds in hex.

- For each object the server computes FNV-1a, a small and fast hash of the named field, and gets a 64-bit integer back. Today the field can be object.metadata.uid or object.metadata.namespace.

- It compares that integer with your hash range, written as [start, end). The start is inside and the end is outside, so [0x0, 0x8000000000000000) is the lower half of the space.

- Only objects whose integer falls in the range leave the server, for the list response and for every watch event. Your decode cost now covers the objects you own.

- Two separate spans combine with || in one selector, so one replica can claim two ranges in a single request.

Predict: two replicas split the space unevenly
Two replicas split the space. Replica 1 owns [0x0, 0xAAAAAAAAAAAAAAAB) and replica 2 owns the rest, from 0xAAAAAAAAAAAAAAAB to the top of the 64-bit space. At 40,000 changes per minute, how many objects does each one decode?

The easy answer is 20,000 each. That answer is wrong, because the range widths decide the traffic and not the replica count.

replica 1   width 0xAAAAAAAAAAAAAAAB / 2^64 = about 2/3   40,000 x 2/3 = 26,667 per minute
replica 2   the rest = about 1/3                          40,000 x 1/3 = 13,333 per minute

The boundary 0xAAAAAAAAAAAAAAAB sits about two thirds of the way across the 64-bit space. A hash spreads the objects evenly over that space, so a replica gets the fraction of the space it owns.

The two ranges in that question split the space two to one, so the traffic splits two to one. Ownership is now a number range instead of a set of objects, and the widths decide the load.

The design uses one contiguous span per replica instead of fixed virtual buckets, a fixed number of equal slices. It rejected the buckets because moving one boundary relocates only a small part of the space. The design hashes the field rather than use its value directly. It does this because uuidv7 is an id format that sorts by time and so produces sequential ids. So this format would land similar ids next to each other in the space. Uneven ranges create a hot shard, one replica that receives more changes than its share of the work. The fix is to move a boundary.

Draw the [start, end) the five replicas claim so the spans cover 0x0 to 2^64 exactly once. Then compute each span's share of 40,000 changes per minute. Each share is the decode cost that replica keeps.

A replica claims a hash range, so the API server sends it only matching changes.

You expect the replica count to decide the load, but the range widths decide it.

Write both ranges as fractions of the 64-bit hash space and check the shares add up to the whole space.

The filter now runs in the API server, and shardInfo in the list response tells you whether it ran.

## How do you know the filter actually ran?

The section above moves the filter into the API server. Your code now needs to know whether that filter ran.

The server-side filter can silently not run, and no error tells you.

Your controller runs several replicas, each claiming a hash range. Each replica expects only the objects whose hash falls in its range. You now let the API server enforce that ownership. When enforcement breaks, two replicas act on the same change and one action runs twice.

During a rolling upgrade, the control plane mixes versions, and only some API servers have the feature gate that turns this filter on. An old server sees a shardSelector it does not know, so it ignores it and streams the whole collection. The call succeeds, so no error warns you.

Predict: did the filter run?
Your replica sends its shardSelector for [0x0000000000000000, 0x8000000000000000) during a rolling upgrade. The call succeeds, and object changes arrive on the watch stream. Did the filter run, and what in the response proves it?

The likely answer is yes, because the call succeeded. That proves nothing, and the response may carry the full collection, not just your range. The proof is shardInfo, the field in ListMeta, the metadata block of the list response, that echoes the hash range the server applied. Here it is missing, so the server ignored your selector.

- Your replica sends a list and watch request with its shardSelector, the hash range it claims. The request lands on one API server, which during the upgrade may be an old one.

- That server runs without the feature gate, so it sees an unknown option and ignores it. The request succeeds and the filter never runs.

- The list returns every object, and the stream then carries every object change. Your replica decodes every object change instead of only the ones its range holds.

- Your code trusts ownership and processes objects outside its hash range. Every replica again processes every object, so each action runs once per replica.

    your replica 1
    endpoint cache
    one API server
    during a rolling upgrade
    gate on: shardInfo present
    8,000 changes per minute
    the range's share
    gate off: shardInfo absent
    40,000 changes per minute
    the whole collection

    list and watch + shardSelector
    the hash range it claims

    filter ran
    filter ignored

One request during a rolling upgrade, and two responses that both return success. Both responses return success, so the full-set fallback is easy to miss.

So your code needs one rule for every list response. When shardInfo is absent, run the full-set fallback. Treat the response as the whole collection and filter every change in your process again. That is the client-side sharding this feature was meant to delete, so every replica again decodes the whole collection.

- Does the list response carry shardInfo?

- yesthe filter ran, so process only your hash range

- norun the full-set fallback

At alpha you write this check yourself. KEP-5866, the design behind this feature, promises helpers for Beta in client-go, the Go client library for Kubernetes. They would read ListMeta on the list response and filter the events themselves. The plan puts Beta at v1.38, so do not count on them yet.

You can also read the OpenAPI v3 discovery document, the file where the server lists its supported features, before your replica connects. It tells you in advance whether any API server answers with shardInfo.

During a control-plane upgrade the fallback fires at least once per rollout. One replica then decodes the full stream instead of only its range's objects. Two replicas act on one change, so one action runs twice. On the server, apiserver_watch_shards_total shows the feature in use and apiserver_watch_filtered_events_total shows the filter working.

One check worth adding is a freshness alarm on what your watchers saw last. The shardInfo check is the same shape. Check for the echo, and filter client-side when it is missing.

Trust a hash range only when the list response echoes it back in shardInfo.

You read success as proof the filter ran, so two replicas act on one change.

Check one list response for shardInfo, and filter client-side when it is missing.

Watching the whole collection has a cost you can now name. Each replica reads the whole collection, and when shardInfo is missing every replica again pays for the full stream. Who assigns the hash ranges and hands one over with no gap and no overlap stays unsolved, and that handover is where duplicate actions come from.

Who assigns the hash ranges is unanswered, and you must work out what each replica still pays for.

## Checkpoint: your endpoint cache at five replicas

Your endpoint-caching watcher runs three replicas now, and the collection changes 40,000 objects per minute. Each change must cross the network and pass a decoder first. With client-side sharding, each replica hashes the object uid and keeps one hash range, a contiguous slice of the 64-bit hash space it owns. It discards every object outside that range.

Answer two things. What does each replica receive and decode per minute, and what do the three cost together? Then name what you check before you trust a shardSelector to divide that cost, and what your code does when the check fails.

Answer sketch

Part 1. Client-side sharding divides the actions, but it does not divide the stream. The API server sends every change to every watcher, so each replica decodes all 40,000 changes per minute. Your filter runs after both costs are paid. The three replicas decode 120,000 objects per minute to act on 40,000.

Five replicas, the running case, keep 40,000 objects of work and multiply the client-side decode to 200,000 per minute.

Every value in the table is arithmetic on the scenario’s 40,000 changes per minute and uniform hashing, not a measurement. No source behind this lesson measures the CPU and memory that decoding costs.

SetupDecoded per replica, per minuteActed on per replica, per minuteDecoded by all replicas, per minute

One replica today, no sharding40,00040,00040,000

Three replicas, client-side sharding, even ranges40,00013,333120,000

Three replicas, shardSelector on even ranges, echoed in shardInfoabout 13,333about 13,333about 40,000

Three replicas, ranges half, quarter, quarter20,000 / 10,000 / 10,00020,000 / 10,000 / 10,00040,000

Selector sent, shardInfo absent40,00013,333120,000

Five replicas, client-side sharding40,0008,000200,000

Five replicas, shardSelector on even rangesabout 8,000about 8,000about 40,000

Part 2. Check the list response for shardInfo, the field in ListMeta that echoes your shardSelector back. An echo means the filter ran on this request. Without it the server returned the full collection, so the full-set fallback runs and your code keeps filtering by hash range. A rolling upgrade mixes old and new API servers, and an old one ignores the selector.

## Sources

- kubernetes.io blog, 6 May 2026 (read 2026-10-20): the announcement post gave the N × full-stream formula, the shardSelector field and the shardInfo echo. High confidence, read in full.

- KEP-5866 (read 2026-10-20): the design doc gave the hash-range contract, the hot-shard failure mode and the Beta fallback plan. High confidence.

- Kubernetes API Concepts (read 2026-10-20): documented the ShardSelector as API contract, alpha since v1.36. High confidence, but the same publisher as the post.

- Ellie Huxtable, 2023 (read 2026-10-20): a production account of the same scaling wall. Confidence high for what it reports, and its numbers are self-reported.

- kube-state-metrics sharding doc (2026-10-20): returned 404 and gave nothing, so its wording is not used.

- No source here measures the win. The post and KEP-5866 report no benchmark, and KEP-5866 requires one for Beta.