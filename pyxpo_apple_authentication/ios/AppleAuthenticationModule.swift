import AuthenticationServices
import UIKit

/// Sign in with Apple on ASAuthorizationController. Errors reply as "ERR_CODE: message" for the Python side.
final class AppleAuthenticationModule: PxModule {
    static let moduleName = "AppleAuthentication"

    private var pending: Request?

    required init() {}

    func call(_ ctx: PxModuleContext, _ method: String, _ args: [Any], _ reply: @escaping PxReply) {
        switch method {
        case "isAvailable": reply(true, nil)
        case "signIn": signIn(ctx, (args.first as? [String: Any]) ?? [:], reply)
        case "credentialState":
            guard let user = args.first as? String else { reply(nil, "ERR_REQUEST_FAILED: no user"); return }
            ASAuthorizationAppleIDProvider().getCredentialState(forUserID: user) { state, error in
                if let e = error { reply(nil, "ERR_REQUEST_FAILED: \(e.localizedDescription)"); return }
                switch state {
                case .revoked: reply(0, nil)
                case .authorized: reply(1, nil)
                case .transferred: reply(3, nil)
                default: reply(2, nil)
                }
            }
        default: reply(nil, "unknown native call AppleAuthentication.\(method)")
        }
    }

    private func signIn(_ ctx: PxModuleContext, _ o: [String: Any], _ reply: @escaping PxReply) {
        guard pending == nil else { reply(nil, "ERR_IN_PROGRESS: a sign-in is already in progress"); return }
        guard let window = ctx.presenter()?.view.window else {
            reply(nil, "ERR_REQUEST_FAILED: no window to present from"); return
        }
        let request = ASAuthorizationAppleIDProvider().createRequest()
        var scopes: [ASAuthorization.Scope] = []
        for s in (o["scopes"] as? [Int]) ?? [] { scopes.append(s == 0 ? .fullName : .email) }
        request.requestedScopes = scopes
        if let state = o["state"] as? String, !state.isEmpty { request.state = state }
        if let nonce = o["nonce"] as? String, !nonce.isEmpty { request.nonce = nonce }
        let r = Request(window: window) { [weak self] result, error in
            self?.pending = nil
            reply(result, error)
        }
        pending = r
        let controller = ASAuthorizationController(authorizationRequests: [request])
        controller.delegate = r
        controller.presentationContextProvider = r
        r.controller = controller
        controller.performRequests()
    }
}

private final class Request: NSObject, ASAuthorizationControllerDelegate,
    ASAuthorizationControllerPresentationContextProviding {
    let window: UIWindow
    let done: (Any?, String?) -> Void
    var controller: ASAuthorizationController?

    init(window: UIWindow, done: @escaping (Any?, String?) -> Void) {
        self.window = window
        self.done = done
    }

    func presentationAnchor(for controller: ASAuthorizationController) -> ASPresentationAnchor { window }

    func authorizationController(controller: ASAuthorizationController,
                                 didCompleteWithAuthorization authorization: ASAuthorization) {
        guard let c = authorization.credential as? ASAuthorizationAppleIDCredential else {
            done(nil, "ERR_INVALID_RESPONSE: not an Apple ID credential"); return
        }
        var name: Any = NSNull()
        if let n = c.fullName {
            name = [
                "namePrefix": n.namePrefix ?? NSNull(), "givenName": n.givenName ?? NSNull(),
                "middleName": n.middleName ?? NSNull(), "familyName": n.familyName ?? NSNull(),
                "nameSuffix": n.nameSuffix ?? NSNull(), "nickname": n.nickname ?? NSNull(),
            ]
        }
        func text(_ d: Data?) -> Any { d.flatMap { String(data: $0, encoding: .utf8) } ?? NSNull() }
        done([
            "user": c.user, "state": c.state ?? NSNull(), "fullName": name, "email": c.email ?? NSNull(),
            "realUserStatus": c.realUserStatus.rawValue, "identityToken": text(c.identityToken),
            "authorizationCode": text(c.authorizationCode),
        ], nil)
    }

    func authorizationController(controller: ASAuthorizationController, didCompleteWithError error: Error) {
        let code: String
        switch (error as? ASAuthorizationError)?.code {
        case .canceled: code = "ERR_REQUEST_CANCELED"
        case .failed: code = "ERR_REQUEST_FAILED"
        case .invalidResponse: code = "ERR_INVALID_RESPONSE"
        case .notHandled: code = "ERR_REQUEST_NOT_HANDLED"
        case .notInteractive: code = "ERR_REQUEST_NOT_INTERACTIVE"
        default: code = "ERR_REQUEST_UNKNOWN"
        }
        done(nil, "\(code): \(error.localizedDescription)")
    }
}
