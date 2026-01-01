// Package handler provides Connect-RPC handlers for the R2T4 server.
package handler

import (
	"context"
	"time"

	"connectrpc.com/connect"
	r2t4v1 "github.com/evren/r2t4/server/gen/r2t4/v1"
	"github.com/evren/r2t4/server/gen/r2t4/v1/r2t4v1connect"
	"github.com/evren/r2t4/server/internal/storage"
)

// AdminHandler implements the AdminService.
type AdminHandler struct {
	r2t4v1connect.UnimplementedAdminServiceHandler
	storage   *storage.Storage
	version   string
	startTime time.Time
}

// NewAdminHandler creates a new AdminHandler.
func NewAdminHandler(s *storage.Storage, version string) *AdminHandler {
	return &AdminHandler{
		storage:   s,
		version:   version,
		startTime: time.Now(),
	}
}

// GetHealth returns server health and version info.
func (h *AdminHandler) GetHealth(
	ctx context.Context,
	req *connect.Request[r2t4v1.GetHealthRequest],
) (*connect.Response[r2t4v1.GetHealthResponse], error) {
	return connect.NewResponse(&r2t4v1.GetHealthResponse{
		Status:            "ok",
		Version:           h.version,
		UptimeSeconds:     int64(time.Since(h.startTime).Seconds()),
		ServerTimestampMs: time.Now().UnixMilli(),
	}), nil
}

// ListDevices returns all known devices.
func (h *AdminHandler) ListDevices(
	ctx context.Context,
	req *connect.Request[r2t4v1.ListDevicesRequest],
) (*connect.Response[r2t4v1.ListDevicesResponse], error) {
	devices, err := h.storage.ListDevices()
	if err != nil {
		return nil, connect.NewError(connect.CodeInternal, err)
	}

	var protoDevices []*r2t4v1.DeviceSummary
	for _, d := range devices {
		protoDevices = append(protoDevices, &r2t4v1.DeviceSummary{
			DeviceId:        d.DeviceID,
			FirstSeenMs:     d.FirstSeenMs,
			LastSeenMs:      d.LastSeenMs,
			AudioChunkCount: d.AudioChunkCount,
			ImageFrameCount: d.ImageFrameCount,
			PromptCount:     d.PromptCount,
			StorageBytes:    d.StorageBytes,
		})
	}

	return connect.NewResponse(&r2t4v1.ListDevicesResponse{
		Devices: protoDevices,
	}), nil
}

// ListFiles returns files for a device.
func (h *AdminHandler) ListFiles(
	ctx context.Context,
	req *connect.Request[r2t4v1.ListFilesRequest],
) (*connect.Response[r2t4v1.ListFilesResponse], error) {
	msg := req.Msg

	// Convert file type enum
	var fileType string
	switch msg.FileType {
	case r2t4v1.FileType_FILE_TYPE_AUDIO:
		fileType = storage.FileTypeAudio
	case r2t4v1.FileType_FILE_TYPE_IMAGE:
		fileType = storage.FileTypeImage
	case r2t4v1.FileType_FILE_TYPE_PROMPT:
		fileType = storage.FileTypePrompt
	default:
		fileType = ""
	}

	files, total, err := h.storage.ListFiles(
		msg.DeviceId,
		fileType,
		msg.StartTimestampMs,
		msg.EndTimestampMs,
		int(msg.Limit),
		int(msg.Offset),
	)
	if err != nil {
		return nil, connect.NewError(connect.CodeInternal, err)
	}

	var protoFiles []*r2t4v1.FileSummary
	for _, f := range files {
		var ft r2t4v1.FileType
		switch f.FileType {
		case storage.FileTypeAudio:
			ft = r2t4v1.FileType_FILE_TYPE_AUDIO
		case storage.FileTypeImage:
			ft = r2t4v1.FileType_FILE_TYPE_IMAGE
		case storage.FileTypePrompt:
			ft = r2t4v1.FileType_FILE_TYPE_PROMPT
		}

		protoFiles = append(protoFiles, &r2t4v1.FileSummary{
			FileId:      f.FileID,
			FileType:    ft,
			TimestampMs: f.TimestampMs,
			SizeBytes:   f.SizeBytes,
			DurationMs:  f.DurationMs,
			Width:       f.Width,
			Height:      f.Height,
			Path:        f.Path,
		})
	}

	return connect.NewResponse(&r2t4v1.ListFilesResponse{
		Files:      protoFiles,
		TotalCount: total,
	}), nil
}

// GetFile returns a file's contents.
func (h *AdminHandler) GetFile(
	ctx context.Context,
	req *connect.Request[r2t4v1.GetFileRequest],
) (*connect.Response[r2t4v1.GetFileResponse], error) {
	// Parse device ID and file ID from the full file ID
	// Format: device_id/path/to/file
	_ = req.Msg.FileId // TODO: implement file retrieval

	// For now, we need the device ID passed separately or encoded in file ID
	// This is a simplified implementation - in practice you'd parse the path
	return nil, connect.NewError(connect.CodeUnimplemented, nil)
}

// DeleteFiles deletes specified files.
func (h *AdminHandler) DeleteFiles(
	ctx context.Context,
	req *connect.Request[r2t4v1.DeleteFilesRequest],
) (*connect.Response[r2t4v1.DeleteFilesResponse], error) {
	// Simplified - would need device ID
	return connect.NewResponse(&r2t4v1.DeleteFilesResponse{
		DeletedCount: 0,
	}), nil
}

// ClearDevice clears all data for a device.
func (h *AdminHandler) ClearDevice(
	ctx context.Context,
	req *connect.Request[r2t4v1.ClearDeviceRequest],
) (*connect.Response[r2t4v1.ClearDeviceResponse], error) {
	deleted, bytes, err := h.storage.ClearDevice(req.Msg.DeviceId)
	if err != nil {
		return connect.NewResponse(&r2t4v1.ClearDeviceResponse{
			Success:      false,
			ErrorMessage: err.Error(),
		}), nil
	}

	return connect.NewResponse(&r2t4v1.ClearDeviceResponse{
		DeletedCount: deleted,
		BytesFreed:   bytes,
		Success:      true,
	}), nil
}

// GetStats returns storage statistics.
func (h *AdminHandler) GetStats(
	ctx context.Context,
	req *connect.Request[r2t4v1.GetStatsRequest],
) (*connect.Response[r2t4v1.GetStatsResponse], error) {
	totalBytes, devices, audio, images, prompts, oldest, newest, err := h.storage.GetStats()
	if err != nil {
		return nil, connect.NewError(connect.CodeInternal, err)
	}

	return connect.NewResponse(&r2t4v1.GetStatsResponse{
		TotalStorageBytes: totalBytes,
		DeviceCount:       int32(devices),
		TotalAudioChunks:  audio,
		TotalImageFrames:  images,
		TotalPrompts:      prompts,
		OldestDataMs:      oldest,
		NewestDataMs:      newest,
	}), nil
}
