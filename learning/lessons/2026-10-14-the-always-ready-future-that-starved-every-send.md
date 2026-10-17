In the last phase you could interleave ready tasks with an event loop, and you trusted the runtime's fairness limits to keep any one task from starving the rest. That trust breaks on a Discord voice server after the edge migration: eight Tokio worker loops each poll a packet receive future and a flush timer, and at European peaks in February 2026 users in Bucharest and Stockholm see pings above 500ms while nothing in the code blocks.

The loop never sleeps and no send is slow. Packets wait in a queue that the runtime reaches less and less often, for minutes at a time, even though the fair-polling budget fires exactly as designed. This lesson answers why a fairness budget counted in polls empties in microseconds at precisely the moment you need it most, and how to replace it with a budget counted in the one thing your users actually feel, wall-clock time.

This lesson teaches one idea. It is stated here so you can see where the lesson is going. It will read more clearly once it has been explained below, so come back to it at the end.

- A runtime's generous yield budget fails exactly at peak load, because at peak the budget empties in microseconds while the same ready future wins every re-poll. Predict starvation in his own select loops and decide to put a time budget on the cheap branch instead of trusting the runtime default.

## What did Bucharest and Stockholm actually see?

Two European cities saw pings above 500ms, and every network theory died in minutes.

By February 2026, users in Bucharest and Stockholm reported voice pings above 500ms. Both regions had migrated to the edge in late 2025, and their traffic now ran on eight worker threads per host. Each worker is a Rust task running Discord's SFU, the server that relays voice packets between call participants.

Inside each worker sits an event loop, one thread that polls a set of waiting tasks and runs whichever is ready. Discord's loop polls two things: a recv future that pulls packets off the socket, and a flush timer that pushes queued sends out. When traffic is light the loop alternates between them, so the design question of which one wins does not come up.

The obvious theories pointed outward, because packet delay usually lives on the wire:

- A routing anomaly, so the team checked the paths and found them clean.

- A peering problem, but the latency did not split along ISP lines the way Rotterdam had.

- A DDoS flood, but inbound traffic looked normal during the spikes.

The move that settled it was a passive probe, a measurement that watches traffic without changing it. Discord's health-check packets carry a fixed payload signature that is identifiable on the wire. Cloudflare's performance team wrote an eBPF program that timestamped each health-check packet as it moved through the host network stack. This gave the processing time for every health-check on every host, and traffic itself was never touched.

The probe split each packet's path into segments. The physical-NIC to virtual-NIC leg was clean, and the return leg was clean too. The lost time sat inside the VM, which meant inside Discord's own process. Three network theories had failed this bisection in minutes instead of weeks.

EvidenceAll incident numbers come from Discord's own engineering post, the only reporter. The eBPF probe and its timestamps are their account, and the SFU is closed source, so nothing here was independently verified.

Knowing the stall was inside the process still left the question of which part. The answer came from a metric Discord already exported: media_batch.latency_microseconds, the time a packet waits in the send queue before the flush sends it. Its baseline was about 1ms, and during European spikes it climbed to hundreds of milliseconds. Receive time was fine. Packets arrived, waited in a queue the loop rarely reached, all while the loop stayed busy and the runtime's fairness mechanism fired exactly as designed.

Predict: the loop polls recv first and the flush timer second, and at peak recv is ready on every poll. The yield budget fires on schedule. Why does send-queue latency climb anyway?Because readiness, not order, decides what runs next. After each yield the loop re-picks a ready branch, and recv is ready every single time, so the timer's turn keeps sliding. The rest of the lesson walks the mechanism.

Time the queue, not just the sends: the damage was send-queue wait, not slow sends.

Clean logs plus a healthy network do not clear your own loop; bisect the path first.

Find one queue-wait metric in a system you run, and check its baseline.

The probe placed the stall inside Discord's process but not inside which line of it. The next section opens the loop itself and asks why the always-ready branch wins every time.

## Why does the always-ready branch win every time?

The probe placed the stall inside Discord's process but not inside which line of it. So the next step is to open the loop itself.

Each of the eight workers runs one select! over two branches. A recv future pulls packets off the socket, and a flush timer drains the send queue. At peak, packets arrive faster than any loop can empty the socket. So the receive buffer is never empty, and a recv poll on a non-empty buffer returns ready at once.

Predict: eight workers poll recv first and the flush timer second, and at peak recv is ready on every poll. Tokio yields every 128 polls. Does send-queue latency stay near its 1ms baseline?The reasonable guess is yes, because Tokio's yield budget exists to stop one branch from starving another. It does not. The budget counts polls, not time. 128 polls of an always-ready future cost a few microseconds, so the timer starves between yields.

The mechanism runs in three steps, repeated thousands of times per second.

- The select picks a ready branch, and recv is ready, so the loop reads a packet in a few microseconds and queues the reply for the flush timer.

- After 128 such polls, Tokio's cooperative budget, the number of polls one task may run before the runtime forces a yield, fires. The source at tag tokio-1.40.0 sets it to Budget(Some(128)) with the comment "chosen somewhat arbitrarily."

- The yield hands control back to the scheduler, which re-polls the task, and recv is still ready, so the same branch wins again and the timer's turn slides further out.

The failure is a wrong unit. Tokio meant "do not starve other tasks for too long", but the budget measures work, not time. At peak, 128 polls take microseconds. Queue latency climbs from about 1ms to hundreds of milliseconds while the fairness mechanism fires exactly as designed.

~1 mssend-queue baseline

100s of msqueue latency at peak

128 pollsTokio yield budget

The fix changed the unit from polls to wall-clock time. Discord added a send budget, a deadline on how long packets may wait in the send queue. If 9ms had passed since the last flush, recv was disabled in the select! for that one poll. With recv not ready, the select had to run the timer, the queue flushed, and p99 dropped immediately.

EvidenceThe 1ms-to-hundreds-of-milliseconds rise, the 9ms constant, and the p99 recovery are Discord's own measurements, reported in their engineering post. The SFU is closed source, so the select interplay is their reconstruction. The 128-poll budget is verified in Tokio source at tag tokio-1.40.0, tokio/src/runtime/coop.rs. The rationale for 9ms over 5 or 20 is not explained.

A poll-count budget fails at peak, because the same ready future wins every re-poll.

Trusting the runtime's fairness default: it is sized for average load, not yours.

Find a select in your code and ask which branch is always ready under load.

Discord fixed one loop in one SFU, so the open question is where this pattern lives in your own stack.

## Where does this pattern live in your own stack?

Discord fixed its loop with a deadline, and yours can hide the same shape.

The bug was never about voice servers or Rust. It lives in any pipeline where two branches share one loop. One branch is a cheap read that is ready again on every poll as load rises. The other is a timed write, a flush or a commit, that runs only when the loop reaches it. Each read stays cheap, so nothing in the loop looks slow, but the delay collects on the timed branch's queue.

A voice-agent backend you could build is this workload at small scale. An event loop is a single thread that polls futures one at a time. In that backend one branch reads audio or tokens from a socket. Another branch flushes outbound messages on a timer. Model speed is not what sets tail latency there. Buffering and the flush timer set it, and the user hears the result as robotic audio.

Predict: in an asyncio agent loop, one task awaits model tokens that keep arriving, and a timer flushes client messages every 20 ms. At peak, does the runtime keep the flush on time?
Not by default. The same two questions decide it as in Discord's loop. They are which branch is ready on every poll under load, and what forces the timed branch to run. In asyncio, an await that completes at once does not hand control back to the loop. When the stream always has a token ready, the reading task can hold the thread. It can run straight through the timer's deadline. Discord's Tokio loop had an explicit 128-poll yield budget as its safety net. Its flush still slid from about 1 ms to hundreds of milliseconds at peak. A scheduler default is sized for average load. So the only flush deadline that survives your peak is one you write in wall-clock time.

Ported across runtimes, only the names change:

- In Tokio, the pair is a select! over a socket read and a flush timer, and the read is ready whenever the receive buffer holds packets.

- In asyncio, the pair is a read task beside a call_later flush, and a satisfied await returns without yielding the loop.

- In Go, the pair is a select over a receive channel and a time.Timer channel, and the receive case runs on every pass that finds the channel non-empty.

The fix that ports between runtimes is not a scheduler setting. It changes what is ready, in two parts. First, give the timed branch a wall-clock deadline, sized from the delay the user can feel. Second, when the deadline passes, make the always-ready branch not ready for one poll. Then the loop has nothing to run but the flush. Discord's send budget is exactly this, 9 ms with recv disabled for one poll when it passed. The same two parts hold in a Go select or an asyncio task. They act on readiness, and readiness is the only thing every scheduler respects. Fairness in an async loop has to be designed, not inherited.

When you audit a loop you own, one question finds it:

- In your peak minute, is one branch ready every time the loop polls?

- nono branch can starve another today, so recheck when traffic doubles

- yes, always the cheap readthe timed branch has no guarantee, so give it a wall-clock deadline and disable the read when it passes

Any loop with an always-ready branch starves its timed branch, whatever the runtime promises.

Calling it a Tokio problem: the same two-branch shape runs in asyncio and Go.

Stamp entry times in your agent system's send queue and look for bending at peak.

You can now read a runtime's fairness knob as a default sized for average load. You can ask of any loop which branch is always ready and how fast its budget empties. The lab lets you run that audit live. It starves a small read-and-flush loop on your own machine. It graphs the queue-wait metric that caught Discord's stall, before and after your fix.

## Lab: starve a loop yourself

The queue-occupancy metric and the wall-clock budget are claims you can test on your own machine in fifteen minutes. You will starve a small loop yourself and watch the curve bend.

Build the Discord loop at small scale. Use an always-ready read branch and a 5ms flush timer on one loop. Feed the loop with a local message generator whose rate you raise.

import asyncio, time

IN = asyncio.Queue(maxsize=10000)
queue_wait = []

async def recv():          # always ready while IN is non-empty
    return await IN.get()

async def worker():
    out, last_flush = [], time.monotonic()
    while True:
        if time.monotonic() - last_flush >= 0.005:
            now = time.monotonic()
            queue_wait.extend(now - t for t, _ in out)
            out.clear(); last_flush = now
        item = await recv()
        out.append(item)

async def gen(rate):       # messages per second
    while True:
        IN.put_nowait((time.monotonic(), 1))
        await asyncio.sleep(1 / rate)

let mut out: Vec<Instant> = Vec::new();
let mut last_flush = Instant::now();
loop {
    tokio::select! {
        item = rx.recv() => out.push(Instant::now()),
        _ = tokio::time::sleep(Duration::from_millis(5)) => {
            for t in out.drain(..) { record(t.elapsed()); }
            last_flush = Instant::now();
        }
    }
}

-  L1 offline Run: python starve.py --rate 2000, recording time-in-queue per flushed item. Raise the rate in steps: 2k, 10k, 50k messages per second. See: queue-wait p99 may hold low while the loop keeps up, then climb once the read branch saturates.

-  L2 offline Find the rate where p99 queue wait first doubles. That is your budget-empties-in-microseconds point: reads now cost so little that any poll-count fairness fires and nothing changes.

-  L3 offline Add the fix at the read branch:

now = time.monotonic()
if now - last_flush >= SEND_BUDGET:   # 5ms wall-clock, recv declawed
    flush(out); last_flush = now; continue

-  L4 offline Rerun the same rates and plot both curves of p99 queue wait against rate. See: the unfixed curve climbs with load, the fixed curve stays flat at the budget.

What you should observe
Below saturation both loops behave the same, because a quiet loop flushes on time without help. Past saturation the unfixed loop's queue wait grows with traffic, while the fixed loop keeps flushing on its 5ms budget. That forced flush is the same shape as the fix behind Discord's immediate p99 drop.

The one output to keep is the two curves, p99 queue wait against message rate, before and after the budget. They are the evidence for the checkpoint and the post.

## Checkpoint

Your multi-agent runtime streams tokens from a model and forwards tool results, all on one asyncio loop. At peak traffic, outbound messages lag by seconds while inbound processing stays fast. Your logging shows no errors and token generation speed is unchanged.

Q1. You suspect the model is slow under load. Before you profile the model, where do you look first, and what one metric do you add?

Answer sketch
Look inside the loop, not the model. Discord's logs were clean too, because the lost time never produced a log line. Add the equivalent of media_batch.latency_microseconds: timestamp each message when it enters the outbound queue and again when the sender flushes it, and export the difference. If p99 queue wait climbs with inbound message rate while model latency stays flat, the loop is starving the flush path, exactly as Discord's recv loop starved its sends.

Q2. Your queue-wait metric confirms how long a packet sits in the send queue: around 1ms at quiet hours, climbing to hundreds of milliseconds at peak. You read that asyncio's event loop yields between callbacks, so you assume a fairness bug is impossible. What is wrong with that reasoning?

Answer sketch
A stream of incoming tokens or tool results is an always-ready source, the same shape as Discord's non-empty recv buffer. Each ready callback is cheap, so many run per millisecond and the runtime's fairness between them costs almost nothing. The timer that flushes your outbound queue can only fire when no ready callback is ahead of it, and each cheap callback delays it by a little, millions of times over. Runtime fairness is sized for average load, which is why it fails exactly at peak.

Q3. Write the smallest fix that does not depend on any runtime's default behaviour. What constant do you pick, and what would you watch to know it is right?

Answer sketch
A wall-clock budget on the cheap branch, the pattern Discord shipped with its 9ms send budget: if more than your budget has passed since the last flush, skip reads for one iteration and flush instead. Discord shipped 9ms, though the post does not explain why that value was chosen. Watch p99 queue wait against message rate, since queue wait is the metric this budget is meant to keep down.

You now have the habit for any loop you read: ask which branch is always ready, and how fast the fairness budget empties at peak traffic.

## Post

The budget that empties in microseconds

The claim: Tokio's 128-poll cooperative budget is sized for average load, so at peak the same always-ready future wins every re-poll and the timed branch starves; the fix is a wall-clock budget on the cheap branch, like Discord's 9ms send budget. What makes it his: the 128 constant verified against tokio-1.40.0 coop.rs, the comment that the value was "chosen somewhat arbitrarily", and the mechanism that travels to asyncio and Go loops.

Starve a loop yourself

The claim: any cheap always-ready read beside a timed write starves the write under load, in code that fits on one screen.

## Sources

- https://discord.com/blog/how-we-moved-discord-voice-to-the-edge — the incident itself: the 500ms pings in Bucharest and Stockholm, the SFU's eight worker loops, the always-ready recv future, media_batch.latency_microseconds rising from ~1ms to hundreds of milliseconds, and the 9ms send budget that fixed p99 in March 2026.

- https://raw.githubusercontent.com/tokio-rs/tokio/tokio-1.40.0/tokio/src/runtime/coop.rs — the 128-poll cooperative budget, verified in Tokio source at tag tokio-1.40.0 as Budget(Some(128)), with the comment that the value "is chosen somewhat arbitrarily".

Every incident number in this lesson comes from one reporter: Discord. The 128 constant and its comment are verified against the Tokio source. How that budget interacts with select! branch randomization in Discord's loop is their reconstruction, because the SFU is closed source. The rationale for 9ms over another value is not explained in the post.