package com.bitejiuyeke.controller;

import com.bitejiuyeke.common.Result;
import com.bitejiuyeke.dto.request.EditImageRequest;
import com.bitejiuyeke.dto.request.MergeImageRequest;
import com.bitejiuyeke.dto.request.SearchImageRequest;
import com.bitejiuyeke.dto.response.EditImageResponse;
import com.bitejiuyeke.dto.response.MergeImageResponse;
import com.bitejiuyeke.dto.response.SearchImageResponse;
import com.bitejiuyeke.dto.response.UploadImageResponse;
import com.bitejiuyeke.entity.ImageFile;
import com.bitejiuyeke.log.ApiLog;
import com.bitejiuyeke.service.FileService;
import jakarta.servlet.http.HttpServletRequest;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.multipart.MultipartFile;

import java.util.List;

@RestController
@Slf4j
@RequestMapping("/api/file")
public class FileController {

    @Autowired
    private FileService fileService;

    @ApiLog
    @PostMapping("/upload/image")
    public Result<UploadImageResponse> uploadImage(
            @RequestParam("file") MultipartFile file,
            HttpServletRequest request
    ) {
        Long userId = (Long) request.getAttribute("userId");
        UploadImageResponse response = fileService.uploadImage(file, userId);
        return Result.success("图片上传成功", response);
    }

    @ApiLog
    @GetMapping("/my-images")
    public Result<List<ImageFile>> myImages(HttpServletRequest request) {
        Long userId = (Long) request.getAttribute("userId");
        List<ImageFile> imageFiles = fileService.myImages(userId);
        return Result.success("查询成功", imageFiles);
    }

    @ApiLog
    @PostMapping("/search")
    public Result<List<SearchImageResponse>> search(
            HttpServletRequest request,
            @RequestParam(value = "query", required = false) String query,
            @RequestParam(value = "file", required = false) MultipartFile file
    ) {
        Long userId = (Long) request.getAttribute("userId");
        SearchImageRequest searchImageRequest = new SearchImageRequest();
        searchImageRequest.setQuery(query);
        searchImageRequest.setFile(file);
        return Result.success("查询成功", fileService.search(userId, searchImageRequest));
    }

    @ApiLog
    @PostMapping("/edit")
    public Result<EditImageResponse> edit(
            @RequestBody @Validated EditImageRequest editImageRequest,
            HttpServletRequest request
    ) {
        Long userId = (Long) request.getAttribute("userId");
        return Result.success("编辑成功", fileService.edit(userId, editImageRequest));
    }

    @ApiLog
    @PostMapping("/merge")
    public Result<MergeImageResponse> merge(
            @RequestBody @Validated MergeImageRequest mergeImageRequest,
            HttpServletRequest request
    ) {
        Long userId = (Long) request.getAttribute("userId");
        return Result.success("合并成功", fileService.merge(userId, mergeImageRequest));
    }

    @ApiLog
    @DeleteMapping("/{id}")
    public Result<Void> deleteImage(
            @PathVariable Long id,
            HttpServletRequest request
    ) {
        Long userId = (Long) request.getAttribute("userId");
        fileService.deleteImage(userId, id);
        return Result.success("删除成功", null);
    }
}
