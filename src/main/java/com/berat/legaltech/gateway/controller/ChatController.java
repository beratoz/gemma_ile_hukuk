package com.berat.legaltech.gateway.controller;

import com.berat.legaltech.gateway.dto.AnalyzeResponse;
import com.berat.legaltech.gateway.dto.ChatRequest;
import com.berat.legaltech.gateway.service.AnalyzeService;
import jakarta.validation.Valid;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api")
public class ChatController {

    private final AnalyzeService analyzeService;

    public ChatController(AnalyzeService analyzeService) {
        this.analyzeService = analyzeService;
    }

    @PostMapping("/chat")
    public ResponseEntity<AnalyzeResponse> chat(@Valid @RequestBody ChatRequest request) {
        AnalyzeResponse response = analyzeService.analyze(request);
        return ResponseEntity.ok(response);
    }
}
