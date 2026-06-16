package com.bitejiuyeke.controller;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.io.FileSystemResource;
import org.springframework.core.io.Resource;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;

@RestController
public class ImageController {

    @Value("${file.upload.dir:../../data/uploads}")
    private String uploadBaseDir;

    @GetMapping("/uploads/images/{filename}")
    public ResponseEntity<Resource> getImage(@PathVariable String filename) {
        Path filePath = Paths.get(uploadBaseDir, "images").resolve(filename).toAbsolutePath().normalize();
        if (!Files.exists(filePath)) {
            return ResponseEntity.notFound().build();
        }
        Resource resource = new FileSystemResource(filePath);
        String contentType;
        try {
            contentType = Files.probeContentType(filePath);
        } catch (Exception e) {
            contentType = "image/png";
        }
        return ResponseEntity.ok()
                .contentType(MediaType.parseMediaType(contentType != null ? contentType : "image/png"))
                .body(resource);
    }
}
