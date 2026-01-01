// Package storage provides file-based storage for uploaded audio and images.
package storage

import (
	"crypto/rand"
	"encoding/hex"
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"sync"
	"time"
)

// Storage handles file-based storage for all uploaded data.
// Thread-safe for concurrent uploads from multiple devices.
//
// Directory structure:
//
//	<data_dir>/
//	├── devices/
//	│   └── <device_id>/
//	│       ├── ambient/
//	│       │   ├── audio/
//	│       │   │   └── <timestamp_ms>_<seq>.wav
//	│       │   └── images/
//	│       │       └── <timestamp_ms>.jpg
//	│       └── prompts/
//	│           └── <prompt_id>/
//	│               ├── audio.wav
//	│               └── response.json
type Storage struct {
	dataDir string
	mu      sync.RWMutex // Protects concurrent access
}

// New creates a new Storage instance with the given data directory.
// Creates the directory structure if it doesn't exist.
func New(dataDir string) (*Storage, error) {
	// Ensure data directory exists
	if err := os.MkdirAll(dataDir, 0755); err != nil {
		return nil, fmt.Errorf("creating data directory: %w", err)
	}

	// Create devices subdirectory
	devicesDir := filepath.Join(dataDir, "devices")
	if err := os.MkdirAll(devicesDir, 0755); err != nil {
		return nil, fmt.Errorf("creating devices directory: %w", err)
	}

	return &Storage{dataDir: dataDir}, nil
}

// SaveAudioChunk saves an audio chunk and returns a unique acknowledgment ID.
func (s *Storage) SaveAudioChunk(deviceID string, timestampMs int64, seqNum int32, data []byte) (string, error) {
	s.mu.Lock()
	defer s.mu.Unlock()

	// Create directory structure
	dir := filepath.Join(s.dataDir, "devices", deviceID, "ambient", "audio")
	if err := os.MkdirAll(dir, 0755); err != nil {
		return "", fmt.Errorf("creating audio directory: %w", err)
	}

	// Filename format: <timestamp_ms>_<seq>.wav
	filename := fmt.Sprintf("%d_%d.wav", timestampMs, seqNum)
	path := filepath.Join(dir, filename)

	if err := os.WriteFile(path, data, 0644); err != nil {
		return "", fmt.Errorf("writing audio file: %w", err)
	}

	ackID := generateAckID()
	return ackID, nil
}

// SaveImageFrame saves an image frame and returns a unique acknowledgment ID.
func (s *Storage) SaveImageFrame(deviceID string, timestampMs int64, data []byte) (string, error) {
	s.mu.Lock()
	defer s.mu.Unlock()

	// Create directory structure
	dir := filepath.Join(s.dataDir, "devices", deviceID, "ambient", "images")
	if err := os.MkdirAll(dir, 0755); err != nil {
		return "", fmt.Errorf("creating images directory: %w", err)
	}

	// Filename format: <timestamp_ms>.jpg
	filename := fmt.Sprintf("%d.jpg", timestampMs)
	path := filepath.Join(dir, filename)

	if err := os.WriteFile(path, data, 0644); err != nil {
		return "", fmt.Errorf("writing image file: %w", err)
	}

	ackID := generateAckID()
	return ackID, nil
}

// SavePromptAudio saves or appends prompt audio data.
// For streaming, this may be called multiple times for the same promptID.
func (s *Storage) SavePromptAudio(deviceID, promptID string, data []byte, appendMode bool) error {
	s.mu.Lock()
	defer s.mu.Unlock()

	// Create directory structure
	dir := filepath.Join(s.dataDir, "devices", deviceID, "prompts", promptID)
	if err := os.MkdirAll(dir, 0755); err != nil {
		return fmt.Errorf("creating prompt directory: %w", err)
	}

	path := filepath.Join(dir, "audio.wav")

	if appendMode {
		f, err := os.OpenFile(path, os.O_APPEND|os.O_CREATE|os.O_WRONLY, 0644)
		if err != nil {
			return fmt.Errorf("opening audio file for append: %w", err)
		}
		defer f.Close()

		if _, err := f.Write(data); err != nil {
			return fmt.Errorf("appending audio data: %w", err)
		}
	} else {
		if err := os.WriteFile(path, data, 0644); err != nil {
			return fmt.Errorf("writing audio file: %w", err)
		}
	}

	return nil
}

// SavePromptResponse saves the response for a prompt.
func (s *Storage) SavePromptResponse(deviceID, promptID, responseJSON string) error {
	s.mu.Lock()
	defer s.mu.Unlock()

	dir := filepath.Join(s.dataDir, "devices", deviceID, "prompts", promptID)
	if err := os.MkdirAll(dir, 0755); err != nil {
		return fmt.Errorf("creating prompt directory: %w", err)
	}

	path := filepath.Join(dir, "response.json")
	if err := os.WriteFile(path, []byte(responseJSON), 0644); err != nil {
		return fmt.Errorf("writing response file: %w", err)
	}

	return nil
}

// DeviceSummary contains summary information about a device.
type DeviceSummary struct {
	DeviceID        string
	FirstSeenMs     int64
	LastSeenMs      int64
	AudioChunkCount int64
	ImageFrameCount int64
	PromptCount     int64
	StorageBytes    int64
}

// ListDevices returns a summary of all known devices.
func (s *Storage) ListDevices() ([]DeviceSummary, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()

	devicesDir := filepath.Join(s.dataDir, "devices")
	entries, err := os.ReadDir(devicesDir)
	if err != nil {
		if os.IsNotExist(err) {
			return nil, nil
		}
		return nil, fmt.Errorf("reading devices directory: %w", err)
	}

	var devices []DeviceSummary
	for _, entry := range entries {
		if !entry.IsDir() {
			continue
		}

		deviceID := entry.Name()
		summary, err := s.getDeviceSummary(deviceID)
		if err != nil {
			// Log but continue with other devices
			continue
		}
		devices = append(devices, summary)
	}

	return devices, nil
}

// getDeviceSummary computes summary statistics for a device.
// Caller must hold at least a read lock.
func (s *Storage) getDeviceSummary(deviceID string) (DeviceSummary, error) {
	summary := DeviceSummary{
		DeviceID:    deviceID,
		FirstSeenMs: 0,
		LastSeenMs:  0,
	}

	deviceDir := filepath.Join(s.dataDir, "devices", deviceID)

	// Count audio files
	audioDir := filepath.Join(deviceDir, "ambient", "audio")
	if entries, err := os.ReadDir(audioDir); err == nil {
		summary.AudioChunkCount = int64(len(entries))
		for _, e := range entries {
			if info, err := e.Info(); err == nil {
				summary.StorageBytes += info.Size()
				modTime := info.ModTime().UnixMilli()
				if summary.FirstSeenMs == 0 || modTime < summary.FirstSeenMs {
					summary.FirstSeenMs = modTime
				}
				if modTime > summary.LastSeenMs {
					summary.LastSeenMs = modTime
				}
			}
		}
	}

	// Count image files
	imagesDir := filepath.Join(deviceDir, "ambient", "images")
	if entries, err := os.ReadDir(imagesDir); err == nil {
		summary.ImageFrameCount = int64(len(entries))
		for _, e := range entries {
			if info, err := e.Info(); err == nil {
				summary.StorageBytes += info.Size()
				modTime := info.ModTime().UnixMilli()
				if summary.FirstSeenMs == 0 || modTime < summary.FirstSeenMs {
					summary.FirstSeenMs = modTime
				}
				if modTime > summary.LastSeenMs {
					summary.LastSeenMs = modTime
				}
			}
		}
	}

	// Count prompts
	promptsDir := filepath.Join(deviceDir, "prompts")
	if entries, err := os.ReadDir(promptsDir); err == nil {
		summary.PromptCount = int64(len(entries))
		for _, e := range entries {
			promptDir := filepath.Join(promptsDir, e.Name())
			if promptEntries, err := os.ReadDir(promptDir); err == nil {
				for _, pe := range promptEntries {
					if info, err := pe.Info(); err == nil {
						summary.StorageBytes += info.Size()
					}
				}
			}
		}
	}

	return summary, nil
}

// FileSummary contains information about a single file.
type FileSummary struct {
	FileID      string
	FileType    string // "audio", "image", "prompt"
	TimestampMs int64
	SizeBytes   int64
	DurationMs  int64 // For audio files
	Width       int32 // For images
	Height      int32 // For images
	Path        string
}

// FileType constants
const (
	FileTypeAudio  = "audio"
	FileTypeImage  = "image"
	FileTypePrompt = "prompt"
)

// ListFiles returns files for a device, optionally filtered by type and time range.
func (s *Storage) ListFiles(deviceID string, fileType string, startMs, endMs int64, limit, offset int) ([]FileSummary, int64, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()

	var files []FileSummary

	deviceDir := filepath.Join(s.dataDir, "devices", deviceID)

	// List audio files
	if fileType == "" || fileType == FileTypeAudio {
		audioDir := filepath.Join(deviceDir, "ambient", "audio")
		if entries, err := os.ReadDir(audioDir); err == nil {
			for _, e := range entries {
				info, err := e.Info()
				if err != nil {
					continue
				}
				// Parse timestamp from filename
				name := e.Name()
				var ts int64
				fmt.Sscanf(name, "%d_", &ts)

				if (startMs == 0 || ts >= startMs) && (endMs == 0 || ts <= endMs) {
					files = append(files, FileSummary{
						FileID:      filepath.Join("ambient", "audio", name),
						FileType:    FileTypeAudio,
						TimestampMs: ts,
						SizeBytes:   info.Size(),
						Path:        filepath.Join(audioDir, name),
					})
				}
			}
		}
	}

	// List image files
	if fileType == "" || fileType == FileTypeImage {
		imagesDir := filepath.Join(deviceDir, "ambient", "images")
		if entries, err := os.ReadDir(imagesDir); err == nil {
			for _, e := range entries {
				info, err := e.Info()
				if err != nil {
					continue
				}
				name := e.Name()
				var ts int64
				fmt.Sscanf(strings.TrimSuffix(name, ".jpg"), "%d", &ts)

				if (startMs == 0 || ts >= startMs) && (endMs == 0 || ts <= endMs) {
					files = append(files, FileSummary{
						FileID:      filepath.Join("ambient", "images", name),
						FileType:    FileTypeImage,
						TimestampMs: ts,
						SizeBytes:   info.Size(),
						Path:        filepath.Join(imagesDir, name),
					})
				}
			}
		}
	}

	// Sort by timestamp descending (newest first)
	sort.Slice(files, func(i, j int) bool {
		return files[i].TimestampMs > files[j].TimestampMs
	})

	totalCount := int64(len(files))

	// Apply pagination
	if offset > 0 && offset < len(files) {
		files = files[offset:]
	} else if offset >= len(files) {
		files = nil
	}

	if limit > 0 && limit < len(files) {
		files = files[:limit]
	}

	return files, totalCount, nil
}

// GetFile returns the contents of a file.
func (s *Storage) GetFile(deviceID, fileID string) ([]byte, string, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()

	path := filepath.Join(s.dataDir, "devices", deviceID, fileID)

	// Security: ensure path is within device directory
	absPath, err := filepath.Abs(path)
	if err != nil {
		return nil, "", fmt.Errorf("invalid path: %w", err)
	}
	deviceDir := filepath.Join(s.dataDir, "devices", deviceID)
	absDeviceDir, _ := filepath.Abs(deviceDir)
	if !strings.HasPrefix(absPath, absDeviceDir) {
		return nil, "", fmt.Errorf("access denied: path outside device directory")
	}

	data, err := os.ReadFile(path)
	if err != nil {
		return nil, "", fmt.Errorf("reading file: %w", err)
	}

	// Determine content type
	contentType := "application/octet-stream"
	if strings.HasSuffix(fileID, ".wav") {
		contentType = "audio/wav"
	} else if strings.HasSuffix(fileID, ".jpg") || strings.HasSuffix(fileID, ".jpeg") {
		contentType = "image/jpeg"
	} else if strings.HasSuffix(fileID, ".json") {
		contentType = "application/json"
	}

	return data, contentType, nil
}

// DeleteFiles deletes the specified files.
func (s *Storage) DeleteFiles(deviceID string, fileIDs []string) (int, []string, error) {
	s.mu.Lock()
	defer s.mu.Unlock()

	var deleted int
	var failed []string

	deviceDir := filepath.Join(s.dataDir, "devices", deviceID)
	absDeviceDir, _ := filepath.Abs(deviceDir)

	for _, fileID := range fileIDs {
		path := filepath.Join(deviceDir, fileID)
		absPath, err := filepath.Abs(path)
		if err != nil || !strings.HasPrefix(absPath, absDeviceDir) {
			failed = append(failed, fileID)
			continue
		}

		if err := os.Remove(path); err != nil {
			failed = append(failed, fileID)
			continue
		}
		deleted++
	}

	return deleted, failed, nil
}

// ClearDevice deletes all data for a device.
func (s *Storage) ClearDevice(deviceID string) (int64, int64, error) {
	s.mu.Lock()
	defer s.mu.Unlock()

	deviceDir := filepath.Join(s.dataDir, "devices", deviceID)

	// Count files and bytes before deletion
	var fileCount int64
	var byteCount int64

	filepath.Walk(deviceDir, func(path string, info os.FileInfo, err error) error {
		if err != nil {
			return nil
		}
		if !info.IsDir() {
			fileCount++
			byteCount += info.Size()
		}
		return nil
	})

	// Remove the entire device directory
	if err := os.RemoveAll(deviceDir); err != nil {
		return 0, 0, fmt.Errorf("removing device directory: %w", err)
	}

	return fileCount, byteCount, nil
}

// GetStats returns overall storage statistics.
func (s *Storage) GetStats() (totalBytes int64, deviceCount, audioCount, imageCount, promptCount int64, oldestMs, newestMs int64, err error) {
	s.mu.RLock()
	defer s.mu.RUnlock()

	devices, err := s.ListDevices()
	if err != nil {
		return 0, 0, 0, 0, 0, 0, 0, err
	}

	deviceCount = int64(len(devices))
	for _, d := range devices {
		totalBytes += d.StorageBytes
		audioCount += d.AudioChunkCount
		imageCount += d.ImageFrameCount
		promptCount += d.PromptCount

		if oldestMs == 0 || d.FirstSeenMs < oldestMs {
			oldestMs = d.FirstSeenMs
		}
		if d.LastSeenMs > newestMs {
			newestMs = d.LastSeenMs
		}
	}

	return totalBytes, deviceCount, audioCount, imageCount, promptCount, oldestMs, newestMs, nil
}

// generateAckID creates a unique acknowledgment ID.
func generateAckID() string {
	// Use timestamp + random bytes for uniqueness
	ts := time.Now().UnixNano()
	randomBytes := make([]byte, 4)
	rand.Read(randomBytes)
	return fmt.Sprintf("%x-%s", ts, hex.EncodeToString(randomBytes))
}
