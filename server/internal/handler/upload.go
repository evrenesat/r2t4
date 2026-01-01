// Package handler provides Connect-RPC handlers for the R2T4 server.
package handler

import (
	"context"
	"log"
	"time"

	"connectrpc.com/connect"
	r2t4v1 "github.com/evren/r2t4/server/gen/r2t4/v1"
	"github.com/evren/r2t4/server/gen/r2t4/v1/r2t4v1connect"
	"github.com/evren/r2t4/server/internal/storage"
)

// UploadHandler implements the UploadService.
type UploadHandler struct {
	r2t4v1connect.UnimplementedUploadServiceHandler
	storage *storage.Storage
}

// NewUploadHandler creates a new UploadHandler.
func NewUploadHandler(s *storage.Storage) *UploadHandler {
	return &UploadHandler{storage: s}
}

// UploadAudioChunk handles audio chunk uploads.
func (h *UploadHandler) UploadAudioChunk(
	ctx context.Context,
	req *connect.Request[r2t4v1.UploadAudioChunkRequest],
) (*connect.Response[r2t4v1.UploadAudioChunkResponse], error) {
	msg := req.Msg

	// Validate request
	if msg.Device == nil || msg.Device.DeviceId == "" {
		return connect.NewResponse(&r2t4v1.UploadAudioChunkResponse{
			Success:      false,
			ErrorMessage: "device_id is required",
		}), nil
	}
	if msg.Metadata == nil {
		return connect.NewResponse(&r2t4v1.UploadAudioChunkResponse{
			Success:      false,
			ErrorMessage: "metadata is required",
		}), nil
	}
	if len(msg.AudioData) == 0 {
		return connect.NewResponse(&r2t4v1.UploadAudioChunkResponse{
			Success:      false,
			ErrorMessage: "audio_data is required",
		}), nil
	}

	// Save the audio chunk
	ackID, err := h.storage.SaveAudioChunk(
		msg.Device.DeviceId,
		msg.Metadata.StartTimestampMs,
		msg.Metadata.SequenceNumber,
		msg.AudioData,
	)
	if err != nil {
		log.Printf("ERROR: Failed to save audio chunk for device %s: %v", msg.Device.DeviceId, err)
		return connect.NewResponse(&r2t4v1.UploadAudioChunkResponse{
			Success:      false,
			ErrorMessage: err.Error(),
		}), nil
	}

	log.Printf("INFO: Saved audio chunk: device=%s seq=%d size=%d bytes ack=%s",
		msg.Device.DeviceId, msg.Metadata.SequenceNumber, len(msg.AudioData), ackID)

	return connect.NewResponse(&r2t4v1.UploadAudioChunkResponse{
		AckId:             ackID,
		Success:           true,
		ServerTimestampMs: time.Now().UnixMilli(),
	}), nil
}

// UploadImageFrame handles image frame uploads.
func (h *UploadHandler) UploadImageFrame(
	ctx context.Context,
	req *connect.Request[r2t4v1.UploadImageFrameRequest],
) (*connect.Response[r2t4v1.UploadImageFrameResponse], error) {
	msg := req.Msg

	// Validate request
	if msg.Device == nil || msg.Device.DeviceId == "" {
		return connect.NewResponse(&r2t4v1.UploadImageFrameResponse{
			Success:      false,
			ErrorMessage: "device_id is required",
		}), nil
	}
	if msg.Metadata == nil {
		return connect.NewResponse(&r2t4v1.UploadImageFrameResponse{
			Success:      false,
			ErrorMessage: "metadata is required",
		}), nil
	}
	if len(msg.ImageData) == 0 {
		return connect.NewResponse(&r2t4v1.UploadImageFrameResponse{
			Success:      false,
			ErrorMessage: "image_data is required",
		}), nil
	}

	// Save the image frame
	ackID, err := h.storage.SaveImageFrame(
		msg.Device.DeviceId,
		msg.Metadata.StartTimestampMs,
		msg.ImageData,
	)
	if err != nil {
		log.Printf("ERROR: Failed to save image frame for device %s: %v", msg.Device.DeviceId, err)
		return connect.NewResponse(&r2t4v1.UploadImageFrameResponse{
			Success:      false,
			ErrorMessage: err.Error(),
		}), nil
	}

	log.Printf("INFO: Saved image frame: device=%s ts=%d size=%d bytes ack=%s",
		msg.Device.DeviceId, msg.Metadata.StartTimestampMs, len(msg.ImageData), ackID)

	return connect.NewResponse(&r2t4v1.UploadImageFrameResponse{
		AckId:             ackID,
		Success:           true,
		ServerTimestampMs: time.Now().UnixMilli(),
	}), nil
}
