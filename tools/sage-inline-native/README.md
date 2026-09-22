# Sage inline native scorer

This is a dependency-free, persistent local scorer for Sage inline completion.
It is deliberately not a general source generator.  The IntelliJ plugin sends
only member names already proved by its concrete Sage type contracts, and this
process returns one of those names or no choice.

## Line protocol v1

One request and one response are exchanged per line while a single persistent
process is alive.  Every non-empty field is lowercase hexadecimal UTF-8 so
source text cannot alter framing.

```
sage-inline-v1 <TAB> prefix-hex <TAB> candidates-hex <TAB> member-context-hex <LF>
sage-inline-v1 <TAB> chosen-name-hex <LF>
```

`candidates-hex` decodes to lines of `member-name<TAB>0-or-1`, where `1`
means callable.  The process only returns a candidate whose name starts with
the prefix.  It chooses a member only when one candidate is already unique or
when that member appears substantially more often in the bounded previous
`.member` observation sequence.  The plugin redacts the source to that
sequence before sending it. Otherwise it returns an empty name.

The protocol intentionally has no model weights, filesystem access, network
access, Sage runtime access, or source execution.  It is a small native
contextual ranker that validates the persistent-process, deadline, cache and
fallback architecture before a separately licensed learned model is selected.

Run its tests with:

```powershell
cargo test --manifest-path tools/sage-inline-native/Cargo.toml
```

To make a current-host development ZIP that embeds the scorer, add the Gradle
property below. The normal build intentionally does not require Rust or embed
a host-specific binary. Marketplace releases currently package the verified
Windows x64 binary; unsupported hosts keep the zero-process semantic fallback.

```powershell
.\gradlew.bat :plugins:sage-core:buildPlugin -Psage.bundle.nativeInlineScorer=true
```
