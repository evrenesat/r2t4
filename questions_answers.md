Project: R2T4 

An Android app that turns an old phone/tablet into a “TV companion” to help a viewer get extra information and have private, ephemeral discussions about what they are watching (YouTube, Netflix, TV). The device sits near/pointed at the TV and continuously:
	•	records ambient audio via the microphone
	•	optionally (but preferably) takes periodic camera photos of the TV screen (e.g., every 1-2 seconds)
	•	uploads audio and images to a user-owned server in chunks (not necessarily real-time streaming)

The key differentiator is privacy/on-prem use: processing and storage stay on the user’s local (or optionally remote) private server, with optional opt-in to third-party APIs if the user lacks compute.

Interaction is wake-word based (e.g., “Hey TV Mate”):
	•	wake word detection should ideally run on-device to avoid noticeable latency
	•	after wake word, the user speaks a prompt/question; the client sends that prompt audio to a separate server endpoint for handling
	•	After MVP2, the server will use the stored recent context (audio + images already uploaded) plus the prompt to produce a response (text first; later optionally audio/TTS and multimodal outputs)

MVP1 / “pipeline-first” phase:
	•	server only saves incoming audio and images to disk with timestamps so they can be correlated
	•	separate storage/endpoint for “prompt audio” after wake word
	•	server returns a simple placeholder text response; client displays it
	•	goal is validating capture/upload reliability and performance on older devices and network conditions
	•	MVP targets local network operation, but remote server should be possible; gRPC is the planned transport


Help me to put together a detailed implementation plan for this idea. I want to use Golang for implementation of server so I can learn Go in the process.
I have no Experience in Java or Kotlin based Android development either. I used Cordova/PhoneGap years ago.

The clarifying questions and answers

A) MVP scope boundaries (what NOT to build yet)
    1.  In MVP, do you want any on-device UI besides “recording” status and showing server response text?
    > an easy to expand settings screen. so I can configure server address, wake word, etc. 
    > this also requires a corresponding server API endpoint to update settings.
    2.  Should MVP support background operation (screen off) continuously, or only while the app is foreground?
    > for MVP, foreground is enough, screen off operation is a nice-to-have for power saving.
    3.  Is “optional camera photos” part of MVP, or can MVP1 be audio-only?
    > for ideal operation, camera photos are needed, so we need to make it part of MVP.
    4.  Do you need multiple TVs / rooms support in MVP, or single device-to-server pairing?
    > out of scope for MVP, but server side data organization should support it.
    5.  Do you need multiple companion devices uploading to the same server simultaneously in MVP?
    > out of scope for MVP, but server side data organization should support it.

B) Target devices and performance envelope
    6.  Minimum Android version you want to support? (e.g., 8/9/10+)    
    > I'm not sure About hardware support, what we can Realistically expect that could handle these requirements. At least Android 8 should be supported.
 I think the hardest part is the wake word detection (while audio, camera capturing and uploading). I think we should try to stay comfortable with as many devices as possible. 
 But in practice, we need to catch the wake words on the device. So it depends on the library that we are going to use for wake word detection. I'm not sure if it will require a specific Android version or some
 amount of CPU power. It depends on that.
    7.  Typical hardware you’ll test on (RAM, CPU class, camera availability)?
    > Motorola Moto Z Play 2016 (Android 8, 3GB RAM, 16MP camera, Snapdragon 625 CPU)
    8.  Expected continuous runtime: hours? days?
    > hours, power saving is just a nice-to-have, not a concern for MVP.
    9.  Is the device allowed to be plugged in always, or must it handle battery constraints?
    > plugged in always is preferred.
    10. Acceptable capture quality for MVP:
> whatever would be enough for speech recognition and image classification (scene processing with AI models). 
lets start with 1280x720 still images every 2 seconds.
mono audio at 16kHz.

    
    12. Do you prefer fixed capture rates or adaptive (reduce photos when network weak / CPU hot)?
> fixed capture rates, configurable from settings.
C) Wake word expectations (MVP vs later)
    13. Does MVP require actual wake-word detection, or is a push-to-talk button acceptable initially?
    > actual wake-word detection is preferred.
    14. If wake word is required in MVP:
    > offline only, tolerate false positives. 
    we need to research user voice recognition at server side to eliminate false positives. (not for mvp but for future)
    15. Do you want wake word to work while app is in background with screen off?
    > this app will be used in a living room, when it's running, it will be always in foreground. 
    > screen off operation is a nice-to-have for power saving.
    16. Is using an existing wake-word engine/library acceptable, or do you insist on training/custom?
    > using an existing wake-word engine/library is preferred.
    17. Do you want a “beep”/haptic confirmation after detection?
    > no, this is not a concern for MVP.

D) Audio pipeline design details
    18. Do you want continuous audio stored as:
    > for MVP, and for local server, raw PCM/WAV chunks is enough and better for reducing load on client.
    > for remote server, compressed (Opus/AAC) chunks is preferred. for MVP1 we will use raw PCM/WAV chunks, but we will use compressed (Opus/AAC) chunks for MVP2.
    •   raw PCM/WAV chunks, or
    •   compressed (Opus/AAC) chunks?

    19. Chunk size preference (time-based): 1s / 5s / 10s / 30s?
    > help me decide chunk size for MVP1. 10s ??
    20. Must chunks be strictly contiguous (no gaps), or is occasional loss acceptable?
    > for MVP1, we will use strictly contiguous chunks.
    21. Should the client keep a local ring buffer in case of network outage, then backfill?
    > purpose of MVP is to validate capture/upload reliability and performance on older devices and network conditions. so I think we should not aim for resiliency.
    22. Maximum local storage usage allowed (e.g., cap at 2GB then delete oldest)?
    > local storage is only needed as a buffer for network outages. so I think we should not aim for resiliency.
    23. Do you want a “session” concept (user starts/stops a session), or always-on with rolling retention?
    > always-on with rolling retention is preferred.

E) Camera capture details
    24. Are “photos every 1–2 seconds” truly needed, or can MVP do 1 image / 5 seconds?
    > I'd like that to be configurable from settings, but 5s is ok for MVP1.
    25. Do you need auto-cropping (detect TV rectangle) in MVP, or just full-frame?
    > we can't expect too much from older devices, so full-frame is preferred for MVP1.
    26. Should photos be captured with flash disabled explicitly (likely yes)?
    > yes,flash is meaningless.
    27. Should camera capture pause when the screen is black/dark (simple brightness heuristic), or always shoot?
    > no, this is not a concern for MVP1.

F) Timestamping and correlation rules
    28. What does “correlate” mean for MVP?
    
    •   Just store timestamps and leave correlation for later, or
    •   Server should pre-index by time buckets?
    > audio and images should be correlated by timestamps on filenames.
    29. How accurate must timestamps be across client and server?
    > timestamps should be accurate to within 1 second.
    > Is client wall-clock trusted, or do you want server-time assignment?
    > client wall-clock is trusted.
    30. Is NTP on the LAN assumed, or should you implement a simple client-server time offset calibration?
    > NTP on the LAN is assumed.
    31. For a wake-word prompt, how much “recent context” do you expect later?
    > when a wake-word is detected, server should already have enough audio and images to generate a response.

G) Network and transport
    32. gRPC over:

    •   plaintext on LAN only, or
    •   TLS even on LAN?
    > plaintext on LAN only is preferred.
    > for remote server, TLS is preferred.
    33. Remote server possibility implies NAT/port-forwarding/VPN:

    •   do you plan to use WireGuard/Tailscale-style networking, or open internet with TLS?
    > open internet with TLS is preferred.
    
    34. Should the client discover the server via:
    > manual IP entry is preferred.

    35. Bandwidth constraints: do you expect Wi-Fi only, or sometimes cellular?
    > Wi-Fi only is preferred.
    36. Do you need upload prioritization:
> when wake-word is detected, upload prompt audio, then continue recording audio and images.
    > we need to solve detecting end of prompt. This is important for MVP. Suggest solutions from open source world. 

H) Identity, pairing, and security (even for MVP)
    37. How should devices authenticate to server?

    •   shared secret token,
    •   mutual TLS,
    •   username/password,
    •   none for LAN MVP?
    > none for LAN MVP is needed. 
    38. Do you want per-device IDs and per-session IDs?
    > just a user defined unique device id is enough, eg. "mytvmate".

    39. Any encryption-at-rest requirement on server disk for MVP?
    > no encryption-at-rest is needed for MVP.
    40. Do you want a simple admin endpoint to list sessions/files, or strictly “dumb storage”?
    > a simple (no auth) endpoint to list sessions/files is preferred.

I) Server storage layout and retention
    41. Where will the Go server run? (Linux box, NAS, Raspberry Pi, Mac mini, etc.)
    > in development a macos, in production a linux box.
    42. Storage layout preference:

    •   /data/device/<id>/session/<id>/audio/<timestamp>.opus
    •   similar for images?
    > yes, but ambient and prompts should be stored in different directories.

    43. Retention policy:

    •   keep everything forever for MVP, or auto-delete after N days?
    > keep everything forever for MVP.

    44. Should server enforce quotas per device?
    > no quotas are needed for MVP.
    45. Do you need a basic “export bundle” feature (zip a time range) in MVP?
    > no export bundle is needed for MVP.

J) API surface (MVP endpoints)
    46. Minimum set of operations you want:

    •   UploadAudioChunk
    •   UploadImageFrame
    •   UploadPromptAudio
    •   GetPlaceholderResponse // why call it placeholder tho? 
    > a propmt upload should return a request ID, and the server should return a response for that request ID (at least that's how I'd do it in REST).
    Again, I'm new to gRPC, so I'm not sure if this is the right way to do it but "placeholder" in the name of the endpoint sounds wrong to me.
    •   Health/Version
    >   settings endpoint is needed for MVP.

Anything else?

    47. For placeholder response: should it be deterministic (echo) or random text?
    > timestamped echo is preferred.
    48. Should the server return an ID for each uploaded chunk (ack) or just success/failure?
    > an ID for each uploaded chunk (ack) is preferred (to ease debugging/logging vs client/server)

K) Observability and debugging requirements
    49. Client logs: should the app expose a “share logs” button?
    50. Server logs: structured JSON logs or plain?
    51. Metrics: do you want Prometheus metrics in MVP?
    52. Do you need end-to-end tracing (probably not for MVP)?
    > simple logging for both client and server is preferred.

L) Failure handling rules (important for “rock solid”)
    53. If upload fails, retry strategy:

    •   exponential backoff is preferred.
    •   max retries?

    54. If server is unreachable for hours, should client:

    >   stop capturing is preferred, and give warning to user.
    •   keep capturing but drop old data,
    •   keep capturing and store locally until full?

    55. What counts as acceptable data loss?
    >  less than 1% chunk loss is preferred.
    56. Should prompt audio still work even if backlog is huge?
    > we should not allow to accumulate a backlog of more than a few minutes of audio and images.
    if server is unavailable, there is no point in keeping the app running.

M) Android implementation approach (given your background)
    57. Are you open to a “native minimal Kotlin” client (recommended for camera/audio reliability), or do you strongly prefer a cross-platform approach?
    > native minimal Kotlin is preferred.
    58. If native: are you willing to accept a small Kotlin codebase focusing only on:

    •   foreground service,
    •   AudioRecord,
    •   CameraX,
    •   gRPC client,
    •   simple UI?
    > I guess yes, I'm new to native Android development, so I'll need help with researching the best practices and optimal approaches.

    59. Do you have any constraint about Play Store distribution, or is this sideload/dev-only?
    > I don't see and limitaiton for play store distribution but it is not a priority for MVP.

    60. Do you need the app to survive OEM battery optimizations (requires special handling)?
    > I'd leave that to the user to handle.

N) Development workflow and handoff format
    61. Do you want the agent handoff as:

    •   a single repo (client + server),
    •   two repos,
    •   or mono-repo with shared protobuf?
    > single repo is preferred. in the future, we will introduce more client options (ios, web, linux, etc.) so we still need to make it easy to share protobufs. 
    62. Preferred build tools:

    •   Server: Go modules, Docker?
    •   Client: Gradle defaults?
    > if it makes sense, okay. I'm new to both Go and native Android development, so I'm open to learning by researching the best practices and optimal approaches.

    63. Do you want automated integration testing:

    •   local fake server,
    •   emulator tests,
    •   or manual only for MVP?
    > manual only for MVP is preferred.
    
    64. What is your “definition of done” for MVP reliability?

    •   e.g., “runs 8 hours on device X with <1% chunk loss”.
    > runs 8 hours on device X with <1% chunk loss is preferred.



	65.	Wake word engine choice for MVP1:
	•	Porcupine acceptable (yes/no)?
	•	If no, choose PocketSphinx vs Precise.
> Porcupine is acceptable for me. But we need to create our data structures and modularity of the system to be able to use different
 libraries or different approach to prompt detection. So for MVP1 I want to use Forspin as I already used it once in the JavaScript environment so I know it is relatively easy to implement and we can benefit from it if users
 are okay with using a non-free binary blob. But we should be able to also let people to implement or precise or pocket sphinx or accepting the delay of loading
 and also to server because in the end this system would be useful mostly only when the server is capable to convert audio
 continuously into string in the text at a very close to real time performance levels otherwise even if we detect prompt wake word quickly on the device,
 if server wouldn't be able to quickly respond, user will still wait too much which is can be acceptable but it is not my goal. I'm aiming for human level responses.  So all in all, expecting server to detect wake word usage and processing rest of the audio as the prompt
 could be a viable option as well. Therefore we need to come with an implementation plan that allows different choices using Porcupine or using server-side wake word detection by just recognizing the wake word out of the whole context of the audio. So for MVP only having Porcupine support is acceptable but the code base, code structure, data structures should expect, should be ready for expanding with different wake word detection approaches.

	66.	Default capture rates (you said configurable; pick initial defaults):
	•	audio chunk duration: keep 5s?
	•	photo interval: 5s?
> audio 5s / photo  2s

	67.	“Settings endpoint” semantics:
	•	Should server be the source of truth for capture rates (client fetches on start), or purely local client settings?
> client related settings only local, setting endpoint is for configuring server side options (later could be only accessible by admin user)
	68.	Backlog threshold:
	•	stop capture when upload queue exceeds 2 minutes of pending data (ok)?
> max 2min backlog is okay. 

Extra Questions/Answers:

R2t4



1. End-of-Prompt Detection (Critical - you mentioned needing solutions)
You mentioned needing to detect when the user finishes speaking their prompt after the wake word. This is crucial for MVP1. Let me clarify:
1. Silence threshold approach: Should we use Voice Activity Detection (VAD) - e.g., consider prompt ended after 1.5-2s of silence? Or do you prefer a fixed maximum prompt duration (e.g., 10 seconds)?
> Voice activity detection could be a good option but even the state-of-the-art production level solutions sometimes feels unnatural to communicate with, I expect the open source solutions I can access to worse, so an alternative approach I can imagine is; 
Letting user set a “prompt end” keyword just like the wake word. we can expect you user to say it when they are done. I don't know if this will be viable using the same wake word detection library on the client-side, probably it might not be possible. then since prompt also will uploaded to server on the fly and will be processed by the server and converted to text, so the moment server detects the “end-word”, it might inform/trigger the client to stop listening for prompt. that can be a fail-safe approach if VAD end up insufficient . But again this doesn't need to be part of MVP 1 at all, just our implementation should take into account this for MVP 2 or later versions. we can just start with simplest VAD solution. 

2. Libraries: Would WebRTC VAD (lightweight, works offline) be acceptable, or do you want to evaluate other options like Silero VAD?
> 
For MVP one we should start with simplest one. But since this solution involves background, ambience audio from TV, next to user's prompt. We can’t always expect user to pause/mute the TV while speaking. Therefore I'd like to experiment with different approaches, different solutions to come up with a workable approach that allows ignoring background audio where just focus on the user's voice. We do not want go into that rabbit hole at the MVP1, but eventually we need to try to also resolve that potential problem.


3. Fallback: What if VAD fails? Should there be a timeout (e.g., max 15 seconds of prompt audio)?
> user configurable time-out would be nice with 15secs as default value.
> push-to-end button on the screen also would be a nice fail-safe even for MVP1.

2. Prompt Audio Handling
1. During prompt capture (after wake word detection), should the app pause uploading ambient audio/images, or continue in parallel?
> Since we also might turn into server-side handling of wake words at some point or at least for some users. For MVP, our  implementation should be kept simple as possible. If pausing is simpler/less error-prone to implement, we should pause, otherwise aim for doing it in parallel. 
2. Should prompt audio be stored as a single file, or chunked like ambient audio?
> single file is okay I think.
3. What happens if the wake word is detected while a previous prompt is still being processed?
> server side should handle it like a job queue, FiFo. Then client should display incoming results like a log output viewer. 

3. UI/UX for MVP
1. What visual feedback should the user see when:
    * Recording/uploading is active (green indicator?)
> yes
    * Wake word is detected (flash color? icon change?)
    * > color change is okay.
    * Prompt is being captured ("Listening..." text?)
> “listening” text with green bg color maybe?
    * Response is received (where to display? overlay? toast? dedicated area?)
> everything can be added to below previous output, again like a log viewer.
> just be sure to always auto-scroll to latest content (unless user scrolls up to read previous outputs, so act similar to other sane shell emulators scrolling behavior. 
2. Should the response text persist on screen, or auto-dismiss after N seconds?
> as explained above. 
3. Do you want a "Stop" button to manually end prompt capture?
> yes, as explained above. But there should be separate “Cancel” and “Done/Send” buttons.

4. Settings Screen Details
1. Which settings should be configurable in MVP1?
    * Server address (required)
    * Device ID (required)
    * Wake word phrase (can this change, or stick with "Hey TV Mate"?)
> IIUC, for Porcelene, wake word cannot be customized by user, but users will need to provide their own activation keys.
(Picevoice allows creating custom wake-word pin files, but I guess that needs to be loaded at build time.)
> Later, in MVP2 we can let it to be customized for other wake word detection libs or for server-side approach.
    * Audio chunk duration (5s default)
    * Photo interval (2s default)
    * What else?
> ideally it should be very easy to populate settings screen from a sqlite settings table
(eg: key_name, value, title, type (int, str, url), description, help_text)
2. Should settings be persisted locally (SharedPreferences) and survive app updates?
> yes they should survive updates.

5. gRPC API Contract Specifics
1. For UploadPromptAudio:
    * Should it be a streaming RPC (client streams audio chunks as user speaks), or a unary RPC (client sends complete audio after user finishes)?
    * If streaming: should server respond with request ID immediately, then final response when done?

> Since later we may opt into server-side wake/end word detection, working with chunks seems to be more flexible.

2. For server response after prompt:
    * Should it be synchronous (blocking until response ready) or async (poll/long-poll)?
Client should be able to continue capturing photo/audio while server processing response.
    * For MVP1 placeholder, what data should be in the response?
> For MVP1, timestamp is enough.

6. Camera Specifics
1. Which camera should be used - front, back, or configurable?
> For MVP, fixed, back-camera. In the future we might allow using front cam for additional context while prompting.
2. Should camera be restarted if it fails, or just log the error and continue audio-only?
> Try to be resilient, log and give warning in case of any errors.
3. Image format: JPEG at what quality level? (85%, 70%?)
70% jpeg is enough. Make it configurable from settings.

7. Server API for Admin/Debug
1. For the "list sessions/files" endpoint:
    * What info to return? (file count, size, time range per device?)
    * Should it return actual file contents/thumbnails, or just metadata?
> for MVP, ideally it should be a simple web page where I can download/play/see audio/image files in the browser. 
2. Should there be a "delete session" or "clear data" endpoint?
> yes!
3. Do you want a simple web UI for this, or just JSON API?
> yes a very simple web ui.

NOTE: I want to be able to directly offer a web-based client or at least an admin interface from the server. So if we are going to use gRPC as the communication protocol and I want to avoid needing a proxy for web interfaces, I want to use connect-go (https://github.com/connectrpc) which offers built in support for web browsers.

8. Error Handling Edge Cases
1. If wake word library fails to initialize, should the app:
    * Run without wake word (push-to-talk fallback)?
> Yes. This should be always an option.
    * Show error and refuse to start?
2. If camera permission denied but mic granted, should the app run audio-only?
> Yes.
3. If server returns an error for a chunk, should that specific chunk be retried or dropped?
> Retried, but buffer doesn’t need to be big, max 2 mins enough.

9. Project Structure Preferences
1. Preferred directory structure? Something like:



r2t4/
├── proto/           # shared protobuf definitions
├── server/          # Go server
├── android/         # Kotlin client
└── docs/            # documentation





2. Do you want CI/CD setup (GitHub Actions) for MVP1, or skip?
> Skip. But create documentation and helper scripts to automate building the server and android packages on MacOS (M4).
3. Code documentation level: minimal inline comments, or more extensive documentation?
> Extensive when it makes sense. I need to learn both Go and Kotlin along the way.

10. Development & Testing Priorities
1. Should we build incrementally or all components together?
    * Option A: Server-first (get storage working, then client)
    * Option B: Client-first (get capture working, mock server)
    * Option C: Parallel (proto definitions first, then both)
> proto defs then server then client. 
2. For the 8-hour reliability test, what metrics should be logged?
    * Chunks sent vs acknowledged?
    * Latency per upload?
    * Memory/CPU usage?
> Log whatever info is easily available, avoid adding extra load on systems or bloat on codebase.

11. Future-Proofing Questions
1. You mentioned iOS/web/Linux clients later. Should MVP1 proto definitions include fields that will be needed later (e.g., room_id, session_id) even if not used?
> Data structures should be future ready as much as possible.
2. For server-side wake word detection (future), should MVP1's proto already support sending continuous audio for server-side processing, or add that later?
> I'm not sure if I get  what you mean. Even when we send audio files in chunks, server still need to continuously process them to keep generating textual context info. So, if needed wake-word can be detected from that. Am I missing something??
