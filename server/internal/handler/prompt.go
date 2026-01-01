// Package handler provides Connect-RPC handlers for the R2T4 server.
package handler

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"sync"
	"time"

	"connectrpc.com/connect"
	r2t4v1 "github.com/evren/r2t4/server/gen/r2t4/v1"
	"github.com/evren/r2t4/server/gen/r2t4/v1/r2t4v1connect"
	"github.com/evren/r2t4/server/internal/storage"
)

// PromptHandler implements the PromptService.
type PromptHandler struct {
	r2t4v1connect.UnimplementedPromptServiceHandler
	storage *storage.Storage

	// Track pending prompts (FIFO queue)
	mu      sync.RWMutex
	prompts map[string]*promptState
	queue   []string // prompt IDs in FIFO order
	queueCh chan struct{}
}

// promptState tracks the state of a prompt being processed.
type promptState struct {
	DeviceID    string
	PromptID    string
	RequestID   string
	Status      r2t4v1.PromptStatus
	AudioData   []byte
	ChunkCount  int
	StartTimeMs int64
	EndTimeMs   int64
	EndReason   r2t4v1.PromptEndReason
	Response    string
	ProcessedMs int64
	Error       string
}

// NewPromptHandler creates a new PromptHandler.
func NewPromptHandler(s *storage.Storage) *PromptHandler {
	h := &PromptHandler{
		storage: s,
		prompts: make(map[string]*promptState),
		queue:   make([]string, 0),
		queueCh: make(chan struct{}, 100),
	}
	// Start background processor (MVP1: just generates placeholder response)
	go h.processQueue()
	return h
}

// SubmitPrompt handles streaming prompt audio uploads.
func (h *PromptHandler) SubmitPrompt(
	ctx context.Context,
	stream *connect.ClientStream[r2t4v1.SubmitPromptRequest],
) (*connect.Response[r2t4v1.SubmitPromptResponse], error) {
	var deviceID, promptID string
	var audioData []byte
	var chunkCount int
	var startTimeMs, endTimeMs int64
	var endReason r2t4v1.PromptEndReason

	// Read all chunks from the stream
	for stream.Receive() {
		msg := stream.Msg()

		// Capture device and prompt ID from first chunk
		if chunkCount == 0 {
			if msg.Device == nil || msg.Device.DeviceId == "" {
				return nil, connect.NewError(connect.CodeInvalidArgument, fmt.Errorf("device_id is required"))
			}
			deviceID = msg.Device.DeviceId
			promptID = msg.PromptId
			startTimeMs = msg.TimestampMs

			if promptID == "" {
				return nil, connect.NewError(connect.CodeInvalidArgument, fmt.Errorf("prompt_id is required"))
			}
		}

		// Append audio data
		audioData = append(audioData, msg.AudioData...)
		chunkCount++
		endTimeMs = msg.TimestampMs

		// Check if this is the final chunk
		if msg.IsFinal {
			endReason = msg.EndReason
			break
		}
	}

	if err := stream.Err(); err != nil && err != io.EOF {
		log.Printf("ERROR: Stream error for prompt %s: %v", promptID, err)
		return nil, connect.NewError(connect.CodeInternal, fmt.Errorf("stream error: %w", err))
	}

	if chunkCount == 0 {
		return nil, connect.NewError(connect.CodeInvalidArgument, fmt.Errorf("no audio data received"))
	}

	// Check if cancelled
	if endReason == r2t4v1.PromptEndReason_PROMPT_END_REASON_CANCELLED {
		log.Printf("INFO: Prompt cancelled: device=%s prompt=%s", deviceID, promptID)
		return connect.NewResponse(&r2t4v1.SubmitPromptResponse{
			PromptId:     promptID,
			RequestId:    "",
			Accepted:     false,
			ErrorMessage: "prompt cancelled by user",
		}), nil
	}

	// Save audio to storage
	if err := h.storage.SavePromptAudio(deviceID, promptID, audioData, false); err != nil {
		log.Printf("ERROR: Failed to save prompt audio: %v", err)
		return nil, connect.NewError(connect.CodeInternal, fmt.Errorf("failed to save audio: %w", err))
	}

	// Generate request ID and queue for processing
	requestID := fmt.Sprintf("req-%d", time.Now().UnixNano())

	h.mu.Lock()
	state := &promptState{
		DeviceID:    deviceID,
		PromptID:    promptID,
		RequestID:   requestID,
		Status:      r2t4v1.PromptStatus_PROMPT_STATUS_QUEUED,
		AudioData:   audioData,
		ChunkCount:  chunkCount,
		StartTimeMs: startTimeMs,
		EndTimeMs:   endTimeMs,
		EndReason:   endReason,
	}
	h.prompts[promptID] = state
	h.queue = append(h.queue, promptID)
	queuePos := len(h.queue)
	h.mu.Unlock()

	// Signal processor
	select {
	case h.queueCh <- struct{}{}:
	default:
	}

	log.Printf("INFO: Prompt queued: device=%s prompt=%s request=%s chunks=%d bytes=%d pos=%d",
		deviceID, promptID, requestID, chunkCount, len(audioData), queuePos)

	return connect.NewResponse(&r2t4v1.SubmitPromptResponse{
		PromptId:      promptID,
		RequestId:     requestID,
		Accepted:      true,
		QueuePosition: int32(queuePos),
	}), nil
}

// GetPromptResponse returns the response for a submitted prompt.
func (h *PromptHandler) GetPromptResponse(
	ctx context.Context,
	req *connect.Request[r2t4v1.GetPromptResponseRequest],
) (*connect.Response[r2t4v1.GetPromptResponseResponse], error) {
	msg := req.Msg

	h.mu.RLock()
	state, exists := h.prompts[msg.PromptId]
	h.mu.RUnlock()

	if !exists {
		return connect.NewResponse(&r2t4v1.GetPromptResponseResponse{
			PromptId: msg.PromptId,
			Status:   r2t4v1.PromptStatus_PROMPT_STATUS_NOT_FOUND,
		}), nil
	}

	// Validate device ID
	if state.DeviceID != msg.DeviceId {
		return connect.NewResponse(&r2t4v1.GetPromptResponseResponse{
			PromptId:     msg.PromptId,
			Status:       r2t4v1.PromptStatus_PROMPT_STATUS_FAILED,
			ErrorMessage: "device_id mismatch",
		}), nil
	}

	return connect.NewResponse(&r2t4v1.GetPromptResponseResponse{
		PromptId:         msg.PromptId,
		Status:           state.Status,
		ResponseText:     state.Response,
		ProcessedAtMs:    state.ProcessedMs,
		ErrorMessage:     state.Error,
		PromptDurationMs: state.EndTimeMs - state.StartTimeMs,
	}), nil
}

// CancelPrompt cancels a pending prompt.
func (h *PromptHandler) CancelPrompt(
	ctx context.Context,
	req *connect.Request[r2t4v1.CancelPromptRequest],
) (*connect.Response[r2t4v1.CancelPromptResponse], error) {
	msg := req.Msg

	h.mu.Lock()
	state, exists := h.prompts[msg.PromptId]
	if exists && state.Status == r2t4v1.PromptStatus_PROMPT_STATUS_QUEUED {
		state.Status = r2t4v1.PromptStatus_PROMPT_STATUS_CANCELLED
		// Remove from queue
		for i, id := range h.queue {
			if id == msg.PromptId {
				h.queue = append(h.queue[:i], h.queue[i+1:]...)
				break
			}
		}
	}
	h.mu.Unlock()

	if !exists {
		return connect.NewResponse(&r2t4v1.CancelPromptResponse{
			PromptId:     msg.PromptId,
			Success:      false,
			ErrorMessage: "prompt not found",
		}), nil
	}

	log.Printf("INFO: Prompt cancelled: prompt=%s", msg.PromptId)

	return connect.NewResponse(&r2t4v1.CancelPromptResponse{
		PromptId: msg.PromptId,
		Success:  true,
	}), nil
}

// processQueue runs in the background to process queued prompts.
// MVP1: Just generates a placeholder timestamp response.
func (h *PromptHandler) processQueue() {
	for range h.queueCh {
		for {
			// Get next prompt from queue
			h.mu.Lock()
			if len(h.queue) == 0 {
				h.mu.Unlock()
				break
			}
			promptID := h.queue[0]
			h.queue = h.queue[1:]
			state := h.prompts[promptID]
			if state == nil || state.Status != r2t4v1.PromptStatus_PROMPT_STATUS_QUEUED {
				h.mu.Unlock()
				continue
			}
			state.Status = r2t4v1.PromptStatus_PROMPT_STATUS_PROCESSING
			h.mu.Unlock()

			// Process the prompt (MVP1: placeholder response)
			processedMs := time.Now().UnixMilli()
			durationMs := state.EndTimeMs - state.StartTimeMs

			// MVP1 placeholder response: timestamp echo
			response := fmt.Sprintf("[%s] Received prompt at %s (duration: %dms, audio: %d bytes, chunks: %d)",
				time.Now().Format("2006-01-02 15:04:05"),
				time.UnixMilli(state.StartTimeMs).Format("15:04:05"),
				durationMs,
				len(state.AudioData),
				state.ChunkCount,
			)

			// Save response to storage
			responseJSON, _ := json.Marshal(map[string]interface{}{
				"prompt_id":    state.PromptID,
				"response":     response,
				"processed_at": processedMs,
				"duration_ms":  durationMs,
			})
			h.storage.SavePromptResponse(state.DeviceID, state.PromptID, string(responseJSON))

			// Update state
			h.mu.Lock()
			state.Status = r2t4v1.PromptStatus_PROMPT_STATUS_COMPLETED
			state.Response = response
			state.ProcessedMs = processedMs
			h.mu.Unlock()

			log.Printf("INFO: Prompt processed: prompt=%s response=%q", promptID, response)
		}
	}
}
