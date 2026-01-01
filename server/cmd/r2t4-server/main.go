// R2T4 Server - TV Companion Backend
//
// This is the main entry point for the R2T4 server.
// It provides gRPC/Connect endpoints for the Android client and a web UI for administration.
package main

import (
	"context"
	"encoding/json"
	"fmt"
	"io/fs"
	"log"
	"net/http"
	"os"
	"os/signal"
	"path/filepath"
	"strings"
	"syscall"
	"time"

	"connectrpc.com/connect"
	"github.com/evren/r2t4/server/gen/r2t4/v1/r2t4v1connect"
	"github.com/evren/r2t4/server/internal/config"
	"github.com/evren/r2t4/server/internal/handler"
	"github.com/evren/r2t4/server/internal/storage"
	"github.com/evren/r2t4/server/internal/web"
	"golang.org/x/net/http2"
	"golang.org/x/net/http2/h2c"
)

// Version and BuildTime are set via ldflags during build.
var (
	Version   = "dev"
	BuildTime = "unknown"
)

func main() {
	// Load configuration
	cfg, err := config.Load()
	if err != nil {
		log.Fatalf("Failed to load configuration: %v", err)
	}

	log.Printf("Starting R2T4 server v%s (built %s)", Version, BuildTime)
	log.Printf("Data directory: %s", cfg.DataDir)
	log.Printf("Listening on: %s", cfg.ListenAddr)

	// Initialize storage
	store, err := storage.New(cfg.DataDir)
	if err != nil {
		log.Fatalf("Failed to initialize storage: %v", err)
	}

	// Create handlers
	uploadHandler := handler.NewUploadHandler(store)
	promptHandler := handler.NewPromptHandler(store)
	adminHandler := handler.NewAdminHandler(store, Version)

	// Create Connect interceptors for logging
	interceptors := connect.WithInterceptors(loggingInterceptor())

	// Create HTTP mux
	mux := http.NewServeMux()

	// Register Connect services
	uploadPath, uploadSvc := r2t4v1connect.NewUploadServiceHandler(uploadHandler, interceptors)
	promptPath, promptSvc := r2t4v1connect.NewPromptServiceHandler(promptHandler, interceptors)
	adminPath, adminSvc := r2t4v1connect.NewAdminServiceHandler(adminHandler, interceptors)

	mux.Handle(uploadPath, uploadSvc)
	mux.Handle(promptPath, promptSvc)
	mux.Handle(adminPath, adminSvc)

	// Register REST-like API endpoints for web UI
	mux.HandleFunc("/api/health", makeJSONHandler(func(r *http.Request) (interface{}, error) {
		return map[string]interface{}{
			"status":          "ok",
			"version":         Version,
			"uptimeSeconds":   int64(time.Since(startTime).Seconds()),
			"serverTimestamp": time.Now().UnixMilli(),
		}, nil
	}))

	mux.HandleFunc("/api/stats", makeJSONHandler(func(r *http.Request) (interface{}, error) {
		totalBytes, devices, audio, images, prompts, oldest, newest, err := store.GetStats()
		if err != nil {
			return nil, err
		}
		return map[string]interface{}{
			"totalStorageBytes": totalBytes,
			"deviceCount":       devices,
			"totalAudioChunks":  audio,
			"totalImageFrames":  images,
			"totalPrompts":      prompts,
			"oldestDataMs":      oldest,
			"newestDataMs":      newest,
		}, nil
	}))

	mux.HandleFunc("/api/devices", makeJSONHandler(func(r *http.Request) (interface{}, error) {
		devices, err := store.ListDevices()
		if err != nil {
			return nil, err
		}
		result := make([]map[string]interface{}, 0, len(devices))
		for _, d := range devices {
			result = append(result, map[string]interface{}{
				"deviceId":        d.DeviceID,
				"firstSeenMs":     d.FirstSeenMs,
				"lastSeenMs":      d.LastSeenMs,
				"audioChunkCount": d.AudioChunkCount,
				"imageFrameCount": d.ImageFrameCount,
				"promptCount":     d.PromptCount,
				"storageBytes":    d.StorageBytes,
			})
		}
		return map[string]interface{}{"devices": result}, nil
	}))

	mux.HandleFunc("/api/files", makeJSONHandler(func(r *http.Request) (interface{}, error) {
		deviceID := r.URL.Query().Get("deviceId")
		if deviceID == "" {
			return nil, fmt.Errorf("deviceId required")
		}

		fileType := r.URL.Query().Get("fileType")
		files, total, err := store.ListFiles(deviceID, fileTypeFromQuery(fileType), 0, 0, 100, 0)
		if err != nil {
			return nil, err
		}

		result := make([]map[string]interface{}, 0, len(files))
		for _, f := range files {
			ft := 0
			switch f.FileType {
			case "audio":
				ft = 1
			case "image":
				ft = 2
			case "prompt":
				ft = 3
			}
			result = append(result, map[string]interface{}{
				"fileId":      f.FileID,
				"fileType":    ft,
				"timestampMs": f.TimestampMs,
				"sizeBytes":   f.SizeBytes,
			})
		}
		return map[string]interface{}{"files": result, "totalCount": total}, nil
	}))

	// Serve files directly
	mux.HandleFunc("/api/file/", func(w http.ResponseWriter, r *http.Request) {
		// Path format: /api/file/{deviceId}/{fileId...}
		path := strings.TrimPrefix(r.URL.Path, "/api/file/")
		parts := strings.SplitN(path, "/", 2)
		if len(parts) < 2 {
			http.Error(w, "Invalid path", http.StatusBadRequest)
			return
		}
		deviceID := parts[0]
		fileID := parts[1]

		// Construct file path safely
		filePath := filepath.Join(cfg.DataDir, "devices", deviceID, fileID)
		absPath, err := filepath.Abs(filePath)
		if err != nil {
			http.Error(w, "Invalid path", http.StatusBadRequest)
			return
		}
		absDataDir, _ := filepath.Abs(cfg.DataDir)
		if !strings.HasPrefix(absPath, absDataDir) {
			http.Error(w, "Access denied", http.StatusForbidden)
			return
		}

		// Determine content type
		contentType := "application/octet-stream"
		if strings.HasSuffix(fileID, ".wav") {
			contentType = "audio/wav"
		} else if strings.HasSuffix(fileID, ".jpg") || strings.HasSuffix(fileID, ".jpeg") {
			contentType = "image/jpeg"
		}

		w.Header().Set("Content-Type", contentType)
		http.ServeFile(w, r, absPath)
	})

	// Clear device endpoint
	mux.HandleFunc("/api/clear/", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
			return
		}
		deviceID := strings.TrimPrefix(r.URL.Path, "/api/clear/")
		if deviceID == "" {
			http.Error(w, "deviceId required", http.StatusBadRequest)
			return
		}

		deleted, bytes, err := store.ClearDevice(deviceID)
		if err != nil {
			http.Error(w, err.Error(), http.StatusInternalServerError)
			return
		}

		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(map[string]interface{}{
			"deletedCount": deleted,
			"bytesFreed":   bytes,
		})
	})

	// Serve embedded web UI
	webFS, err := fs.Sub(web.GetFS(), ".")
	if err != nil {
		log.Fatalf("Failed to get web filesystem: %v", err)
	}
	mux.Handle("/", http.FileServer(http.FS(webFS)))

	// Create server with h2c (HTTP/2 over cleartext) support for Connect
	server := &http.Server{
		Addr:         cfg.ListenAddr,
		Handler:      h2c.NewHandler(mux, &http2.Server{}),
		ReadTimeout:  30 * time.Second,
		WriteTimeout: 30 * time.Second,
	}

	// Handle graceful shutdown
	go func() {
		sigCh := make(chan os.Signal, 1)
		signal.Notify(sigCh, syscall.SIGINT, syscall.SIGTERM)
		<-sigCh

		log.Println("Shutting down server...")
		ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
		defer cancel()

		if err := server.Shutdown(ctx); err != nil {
			log.Printf("Error during shutdown: %v", err)
		}
	}()

	// Start server
	if cfg.IsTLSEnabled() {
		log.Printf("Starting HTTPS server with TLS")
		err = server.ListenAndServeTLS(cfg.TLSCertFile, cfg.TLSKeyFile)
	} else {
		log.Printf("Starting HTTP server (no TLS)")
		err = server.ListenAndServe()
	}

	if err != nil && err != http.ErrServerClosed {
		log.Fatalf("Server error: %v", err)
	}

	log.Println("Server stopped")
}

var startTime = time.Now()

// loggingInterceptor creates a Connect interceptor that logs requests.
func loggingInterceptor() connect.UnaryInterceptorFunc {
	return func(next connect.UnaryFunc) connect.UnaryFunc {
		return func(ctx context.Context, req connect.AnyRequest) (connect.AnyResponse, error) {
			start := time.Now()
			resp, err := next(ctx, req)
			duration := time.Since(start)

			status := "OK"
			if err != nil {
				status = connect.CodeOf(err).String()
			}

			log.Printf("%s %s [%s] %v",
				req.Spec().Procedure,
				req.Peer().Addr,
				status,
				duration,
			)

			return resp, err
		}
	}
}

// makeJSONHandler creates an HTTP handler that returns JSON.
func makeJSONHandler(fn func(*http.Request) (interface{}, error)) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		result, err := fn(r)
		if err != nil {
			http.Error(w, err.Error(), http.StatusInternalServerError)
			return
		}
		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(result)
	}
}

// fileTypeFromQuery converts query parameter to storage file type.
func fileTypeFromQuery(q string) string {
	switch q {
	case "1":
		return "audio"
	case "2":
		return "image"
	case "3":
		return "prompt"
	default:
		return ""
	}
}
