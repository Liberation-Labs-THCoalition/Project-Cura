# Wayfinding — what the survey found, and the one rule that follows

Workflow `cura-presence-wayfinding` (wf_a6a2b36e-70e): 10 agents, 3 designs.
**All three scored 6/10. All three can name a room confidently and wrongly. All
three let a dead battery read as an empty room.**

Full output: `/tmp/claude-1000/-home-asdf/ff2cec31-eb06-4aaf-b8ad-01993f849fc9/tasks/w8p1qi6ul.output`

---

## 1. His security system probably cannot be used

> "Not one of the nine systems offers a documented local API. Ring, SimpliSafe,
> Abode, Arlo and Wyze-sensors are cloud, full stop; ADT Pulse, Vivint, Scout
> and Wyze are unofficial cloud reverse-engineering."

So the premise I started from — interface with what he already owns — is
probably wrong. Plan for zero vendor local API and be pleasantly surprised.

One exception worth a single question: **if the brand is "ADT+", ask whether
the hub appears as a Matter bridge.** That would be a real local API and the
best outcome in the survey.

The brand remains the highest-value missing fact.

## 2. What is actually buildable, and what it costs

One mains-powered mmWave sensor per room running **ESPHome**, no zones
configured. Room identity comes from one-sensor-per-room, not zone geometry.

- ~$35/room prebuilt (Everything Presence One / Lite class)
- ~$10/room as ESP32 + LD2410 if assembled

Home Assistant as the **sensor bus**, explicitly NOT as the answering brain, and
**do not trust its `available` flag as the liveness signal.**

The reason to prefer ESPHome over his existing system is not convenience. It is
the only stack in the survey where a dead sensor is *distinguishable* from an
empty room at the API level — ESPHome's 90-second liveness is source-verified,
and MQTT with a last-will plus `expire_after` gives a window you set. The
cloud-vendor stacks cannot make that distinction at all.

## 3. THE RULE THAT FOLLOWS, and it is not negotiable

**Cura may say where she IS. Cura may not say where she is NOT.**

Every one of the three designs failed on the negative, and the root cause is the
same in each: the claim "this sensor can prove a room empty" was written as a
constant rather than measured.

The winning design had this line:

    CAN_PROVE_NEGATIVE[Modality.MMWAVE] = True

justified in a comment as "sees breathing". **The hardware in its own bill of
materials does not see breathing.** The LD2410/LD2450 are motion and
micro-motion radar, not vital-signs radar, and losing a still sleeping adult
under bedding at 3-4m is that part's best-known failure mode.

That single `True` was the only thing that could ever mark a room CLEAR. It is a
check that cannot fail, written into the design that exists to embody the law.

### The 3:40am walkthrough the judge traced

A dead one-way 433MHz PIR retains `on` in Home Assistant forever — no
availability topic, nothing to expire. The state machine classifies it
NOT_CHARACTERIZED ("I don't know this device"), which the design *permits to
speak positives*, and room fusion says a fresh positive beats everything.

> "She's in the living room."

She is asleep three feet from him in the bedroom — the one room the model
actively ruled out, because the mmWave saw no motion under a duvet.

**A seventy-something man with failing sight walks the length of a dark house on
the strength of a sensor that died six hours earlier.**

### The second one

Home Assistant's container OOMs at 2am. Every entity vanishes. Every sensor
reads NEVER_REPORTED — the state meaning "never commissioned" — so Cura says:

> "I've never had a single reading from the bedroom sensor... Could you feel
> behind the dresser and check the little plug is pushed in?"

A blind man is sent crawling behind furniture at 3am while his wife is missing,
because the model had no state for *the source is gone*.

## 4. The bench test that has to happen before any negative ships

Cheap, concrete, and it either earns the negative or kills it:

> Mount the sensor at its intended height. A person lies still for 60 minutes.
> Log the longest continuous `off` run.

If that run is ever nonzero, mmWave is not negative-capable at that mounting,
CLEAR is unearnable, and the model must be able to say so — which none of the
three currently can.

## 5. Other flaws worth keeping in view

- **One threshold gated both directions.** `stale_after` treated positives and
  negatives identically, leaving a structural ~150s window in which a dying
  sensor reports "not there". Negatives must require strictly tighter freshness
  than positives; the asymmetry is the entire point.
- **`stale_after` was estimated from the wrong clock.** Measured on the presence
  entity, a weekend away makes p99 three days, so a sensor reads "live" for a
  week after it dies.

## 6. What I would build now

Positives only, evidence age always spoken, and no search plan:

> "She's in the kitchen — that's from about a minute ago."
> "The last thing I saw was the hallway, twenty minutes ago. I can't tell you
>  where she is now."

Losing the negative costs the feature that would have told him where *not* to
look. That is a real loss and it is worth it, because the alternative is a
confident wrong room delivered to someone who cannot check it himself.
